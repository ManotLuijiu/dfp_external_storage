frappe.provide("dfp_external_storage.uploader");

// Enhance the FileUploader class for S3 integration
dfp_external_storage.uploader.setup = function () {
  if (!frappe.ui.FileUploader) return;

  // Store original handler
  const originalOnSuccess = frappe.ui.FileUploader.prototype.on_success;

  // Override the method
  frappe.ui.FileUploader.prototype.on_success = function (file, response) {
    // Call original method first
    originalOnSuccess.call(this, file, response);

    // Check if file has S3 storage
    if (
      response.message.file_url &&
      response.message.file_url.startsWith("/file/")
    ) {
      // Show notification for S3 upload file
      frappe.show_alert(
        {
          message: __("File securely uploaded to S3 storage"),
          indicator: "green",
        },
        5
      );
    }
  };

  //   Enhance the "Link" option in file uploader
  if (frappe.ui.FileUploader.prototype.show_link_dialog) {
    const originalShowLinkDialog =
      frappe.ui.FileUploader.prototype.show_link_dialog;

    frappe.ui.FileUploader.prototype.show_link_dialog = function () {
      // Add a button to browse S3 files
      const dialog = originalShowLinkDialog.call(this);

      // Add a button below the link field
      dialog.set_secondary_action(__("Browse S3 Files"), () => {
        dfp_external_storage.uploader.show_s3_browser(dialog);
      });

      return dialog;
    };
  }
};

// Show S3 file browser dialog
dfp_external_storage.uploader.show_s3_browser = function (link_dialog) {
  frappe.call({
    method: "dfp_external_storage.api.get_media_library",
    callback: function (r) {
      if (!r.message) return;
      let files = r.message;
      let d = new frappe.ui.Dialog({
        title: __("Select S3 File"),
        fields: [
          {
            label: __("Storage"),
            fieldname: "storage_filter",
            fieldtype: "Link",
            options: "DFP External Storage",
            change: () => {
              let storage = d.get_value("storage_filter");
              let filtered_files = storage
                ? files.filter((f) => f.dfp_external_storage === storage)
                : files;

              d.fields_dict.file_list.grid.refresh();
              d.fields_dict.file_list.grid.data = filtered_files;
              d.fields_dict.file_list.grid.render_rows();
            },
          },
          {
            label: __("Files"),
            fieldname: "file_list",
            fieldtype: "Table",
            connot_add_rows: true,
            data: files,
            fields: [
              {
                label: __("File"),
                fieldsname: "file_name",
                fieldtype: "Data",
                in_list_view: 1,
                read_only: 1,
              },
              {
                label: __("Private"),
                fieldname: "is_private",
                fieldtype: "Check",
                in_list_view: 1,
                read_only: 1,
              },
              {
                label: __("Get URL"),
                fieldname: "get_url",
                fieldtype: "Button",
                in_list_view: 1,
                click: (evt, doc) => {
                  if (doc.is_private) {
                    // For private files, get a secure presigned URL
                    frappe.call({
                      method: "dfp_external_storage.api.get_presigned_url",
                      args: {
                        file_id: doc.name,
                      },
                      callback: function (r) {
                        if (r.message && r.message.success) {
                          if (link_dialog) {
                            link_dialog.set_value(
                              "url",
                              r.message.presigned_url
                            );
                            d.hide();

                            // Show expiration warning
                            let mins = Math.floor(
                              r.message.expiration_seconds / 60
                            );
                            frappe.show_alert(
                              {
                                message: __(
                                  `Note: This secure link will expire in ${mins} minutes`
                                ),
                                indicator: "orange",
                              },
                              7
                            );
                          }
                        } else {
                          frappe.msgprint(__("Could not generate secure URL"));
                        }
                      },
                    });
                  } else {
                    // For public files, use the file URL directly
                    if (link_dialog) {
                      link_dialog.set_value("url", doc.file_url);
                      d.hide();
                    }
                  }
                },
              },
            ],
          },
        ],
        primary_action_label: __("Cancel"),
        primary_action: () => {
          d.hide();
        },
      });
      d.show();
    },
  });
};

// Initialize the enhancements
$(document).ready(function () {
  dfp_external_storage.uploader.setup();
});
