import { db } from "./db";
import { call } from "@/utils/apiWrapper";
import { generateUUID } from "./uuid";

/**
 * Save a newly created customer for later server synchronization.
 *
 * The customer cache and pending queue are updated atomically.
 * Temporary names are never treated as ERPNext Customer IDs.
 */
export const saveOfflineCustomer = async (customerData, posProfile) => {
    const customerName = String(customerData.customer_name || "").trim();

    if (!customerName) {
        throw new Error("Customer Name is required");
    }

    const offlineId = `pos_customer_${generateUUID()}`;

    const customer = {
        name: offlineId,
        customer_name: customerName,
        mobile_no: customerData.mobile_no || "",
        email_id: customerData.email_id || "",
        customer_group: customerData.customer_group || "",
        territory: customerData.territory || "",
        custom_governorate: customerData.custom_governorate || "",
        custom_district: customerData.custom_district || "",
        pos_profile: posProfile || "",
        offline_pending: true,
        offline_id: offlineId,
    };

    await db.transaction("rw", db.customer_queue, db.customers, async () => {
        await db.customer_queue.add({
            offline_id: offlineId,
            status: "pending",
            timestamp: Date.now(),
            server_customer: null,
            data: customer,
        });

        await db.customers.add(customer);
    });

    return customer;
};

export const getPendingOfflineCustomers = async () => {
    return db.customer_queue
        .where("status")
        .equals("pending")
        .toArray();
};

export const getOfflineCustomer = async (offlineId) => {
    return db.customer_queue.get(offlineId);
};


/**
 * Synchronize locally created customers before dependent invoices.
 * Keep failed records available for subsequent retry.
 */
let customerSyncPromise = null;

const performCustomerSync = async () => {
    const pending = await getPendingOfflineCustomers();
    const result = { success: 0, failed: 0, errors: [] };

    for (const record of pending) {
        try {
            const response = await call(
                "pos_next.api.offline_customers.sync_customer",
                {
                    offline_id: record.offline_id,
                    customer_data: JSON.stringify(record.data),
                    pos_profile: record.data.pos_profile || null,
                }
            );

            const data = response?.message || response;
            const serverCustomer = data?.customer;

            if (!serverCustomer) {
                throw new Error("Customer sync returned no Customer ID");
            }

            await db.transaction(
                "rw",
                db.customer_queue,
                db.customers,
                async () => {
                    const localCustomer = await db.customers.get(record.offline_id);

                    if (localCustomer) {
                        const existingServerCustomer = await db.customers.get(serverCustomer);
                        if (!existingServerCustomer) {
                            await db.customers.put({
                                ...localCustomer,
                                name: serverCustomer,
                                offline_pending: false,
                            });
                        }
                        await db.customers.delete(record.offline_id);
                    }

                    await db.customer_queue.update(record.offline_id, {
                        status: "synced",
                        server_customer: serverCustomer,
                        synced_at: Date.now(),
                    });
                }
            );

            // Notify active POS stores after the local transaction commits.
            window.dispatchEvent(new CustomEvent("offlineCustomerSynced", {
                detail: {
                    offlineId: record.offline_id,
                    serverId: serverCustomer,
                },
            }));

            result.success++;
        } catch (error) {
            result.failed++;
            result.errors.push({
                offline_id: record.offline_id,
                error: error.message || String(error),
            });
        }
    }

    return result;
};

export const syncPendingOfflineCustomers = () => {
    if (customerSyncPromise) return customerSyncPromise;

    customerSyncPromise = performCustomerSync().finally(() => {
        customerSyncPromise = null;
    });

    return customerSyncPromise;
};

/**
 * Resolve a temporary customer ID to the synchronized ERPNext Customer ID.
 * Return null when the customer has not synchronized successfully.
 */
export const resolveOfflineCustomerId = async (customerId) => {
    if (!String(customerId || "").startsWith("pos_customer_")) {
        return customerId;
    }

    const record = await db.customer_queue.get(customerId);

    return record?.status === "synced"
        ? record.server_customer || null
        : null;
};
