# -*- coding: utf-8 -*-
# Copyright (c) 2026, POS Next and contributors
# For license information, please see license.txt

"""Lightweight WhatsApp OTP gate for sensitive POS actions.

A short numeric code is generated, its hash stored in the cache with a TTL
(no DocType / DB column, so this works even before `bench migrate` runs), and
the plain code is delivered over WhatsApp. The confirming endpoint re-verifies
the code before performing the action.

Flow (driven entirely by the action endpoint):
  1. Action called WITHOUT a code while OTP is enabled -> generate + send,
     return ``{"otp_required": True, ...}`` and do nothing else.
  2. Action called WITH the code -> ``verify`` consumes it, action proceeds.
"""

import hashlib
import secrets

import frappe
from frappe import _
from frappe.utils import cint

OTP_TTL_SECONDS = 120          # code is valid for 2 minutes
OTP_MAX_ATTEMPTS = 3           # wrong tries before the code is burned
OTP_DIGITS = 6                 # default length; callers may override per action


def _key(purpose, ref):
	return f"mu_pos_otp:{purpose}:{ref}"


def _hash(code):
	return hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()


def mask_mobile(mobile):
	m = str(mobile or "")
	if len(m) <= 4:
		return m
	return ("•" * (len(m) - 4)) + m[-4:]


def generate_and_send(purpose, ref, mobile, label, digits=OTP_DIGITS):
	"""Create a one-time code, cache its hash, and WhatsApp it to ``mobile``.

	``digits`` sets the code length for this action (vouchers and cash use
	different lengths). Returns an ``otp_required`` payload the client uses to
	show the code box. Raises if there is no destination number or WhatsApp
	delivery fails.
	"""
	from pos_next.api.whatsapp_hook import send_whatsapp

	if not mobile:
		frappe.throw(_("لا يوجد رقم واتساب لإرسال رمز التحقق إليه."))

	digits = cint(digits) or OTP_DIGITS
	code = f"{secrets.randbelow(10 ** digits):0{digits}d}"
	frappe.cache().set_value(
		_key(purpose, ref),
		{"h": _hash(code), "n": 0},
		expires_in_sec=OTP_TTL_SECONDS,
	)

	message = _(
		"رمز التحقق لعملية «{0}»: {1}\nصالح لمدة دقيقتين. لا تشاركه مع أحد."
	).format(label, code)
	if not send_whatsapp(mobile, message):
		# Burn the code so a failed send can't be guessed against.
		frappe.cache().delete_value(_key(purpose, ref))
		frappe.throw(_(
			"تعذّر إرسال رمز التحقق عبر واتساب. تأكد من ربط تطبيق الواتساب ومن صحة الرقم."
		))

	return {
		"otp_required": True,
		"masked_mobile": mask_mobile(mobile),
		"expires_in": OTP_TTL_SECONDS,
		"digits": digits,
	}


def verify(purpose, ref, code):
	"""Validate a submitted code. Consumes it on success; raises otherwise."""
	if not code:
		frappe.throw(_("أدخل رمز التحقق المرسل عبر واتساب."))

	key = _key(purpose, ref)
	data = frappe.cache().get_value(key)
	if not data:
		frappe.throw(_("انتهت صلاحية رمز التحقق أو لم يُطلب بعد. أعد المحاولة."))

	if cint(data.get("n")) >= OTP_MAX_ATTEMPTS:
		frappe.cache().delete_value(key)
		frappe.throw(_("تم تجاوز عدد المحاولات المسموح بها. اطلب رمزًا جديدًا."))

	if _hash(code) != data.get("h"):
		data["n"] = cint(data.get("n")) + 1
		frappe.cache().set_value(key, data, expires_in_sec=OTP_TTL_SECONDS)
		remaining = OTP_MAX_ATTEMPTS - cint(data["n"])
		frappe.throw(_("رمز التحقق غير صحيح. المحاولات المتبقية: {0}.").format(max(0, remaining)))

	# One-time use: remove on success.
	frappe.cache().delete_value(key)
	return True
