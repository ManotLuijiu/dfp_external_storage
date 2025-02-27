frappe.provide("dfp_external_storage.api");

dfp_external_storage.api.get_media_library = function () {
  return frappe.call({
    method: "dfp_external_storage.api.get_media_library",
  });
};

dfp_external_storage.api.get_presigned_url = function (file_id) {
  return frappe.call({
    method: "dfp_external_storage.api.get_presigned_url",
    args: {
      file_id: file_id,
    },
  });
};

dfp_external_storage.api.bulk_offload_files = function (
  storage_name,
  folder,
  limit
) {
  return frappe.call({
    method: "dfp_external_storage.api.bulk_offload_files",
    args: {
      storage_name: storage_name,
      folder: folder,
      limit: limit || 100,
    },
  });
};

// dfp_external_storage.api.get_cdn_url = function (file_doc) {
//   if (!file_doc.dfp_external_storage || !file_doc.dfp_external_storage_s3_key) {
//     return null;
//   }

//   return frappe.call({
//     method: "dfp_external_storage.api.get_cdn_url",
//     args: {
//       storage_name: file_doc.dfp_external_storage,
//       object_key: file_doc.dfp_external_storage_s3_key,
//     },
//   });
// };
