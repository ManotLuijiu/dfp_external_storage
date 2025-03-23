frappe.ui.form.on("DFP External Storage", {
  setup: (frm) => {
    frm.button_remote_files_list = null;
  },

  refresh: function (frm) {
    if (frm.is_new() && !frm.doc.doctypes_ignored.length) {
      frm.doc.doctypes_ignored.push({ doctype_to_ignore: "Data Import" });
      frm.doc.doctypes_ignored.push({ doctype_to_ignore: "Prepared Report" });
      frm.refresh_field("doctypes_ignored");
    }

    if (frm.doc.enabled) {
      frm.button_remote_files_list = frm.add_custom_button(
        __("List files in bucket"),
        () => frappe.set_route("dfp-s3-bucket-list", frm.doc.name)
        // () => frappe.set_route('dfp-s3-bucket-list', { storage: frm.doc.name })
      );
    }

    // Storage type specific actions
    if (frm.doc.type === "Google Drive") {
      // Add Google Drive authentication button
      setup_google_drive_auth(frm);
    } else {
      // Add Test Connection button for S3
      frm
        .add_custom_button(__("Test Connection"), function () {
          frm.events.test_connection(frm);
        })
        .addClass("btn-primary");
    }

    frm.set_query("folders", function () {
      return {
        filters: {
          is_folder: 1,
        },
      };
    });

    frappe.db
      .get_list("DFP External Storage by Folder", {
        fields: ["name", "folder"],
      })
      .then((data) => {
        if (data && data.length) {
          let folders_name_not_assigned = data
            .filter((d) => (d.name != frm.doc.name ? d : null))
            .map((d) => d.folder);
          frm.set_query("folders", function () {
            return {
              filters: {
                is_folder: 1,
                name: ["not in", folders_name_not_assigned],
              },
            };
          });
        }
      });
  },

  type: function (frm) {
    // Show/hide fields based on storage type
    frm.trigger("refresh");
  },

  test_connection: function (frm) {
    if (frm.doc.type === "Google Drive") {
      frm.events.test_google_drive_connection(frm);
    } else {
      frm.events.test_s3_connection(frm);
    }
  },

  test_s3_connection: function (frm) {
    // frappe.show_message(__("Testing S3 Connection..."));
    frappe.show_alert(
      {
        message: __("Testing S3 Connection..."),
        indicator: "blue",
      },
      15
    ); // Shows for 15 seconds

    // Preapare for API call - collect all the necessary fields
    let data = {
      endpoint: frm.doc.endpoint,
      secure: frm.doc.secure,
      bucket_name: frm.doc.bucket_name,
      region: frm.doc.region,
      access_key: frm.doc.access_key,
      // Secret key won't be included if the doc is saved
      // It will use the stored encrypted value in that case
      secret_key: frm.is_new() ? frm.doc.secret_key : undefined,
      storage_type: frm.doc.type,
    };

    frappe.call({
      method:
        "dfp_external_storage.dfp_external_storage.doctype.dfp_external_storage.dfp_external_storage.test_s3_connection",
      args: {
        doc_name: frm.doc.name,
        connection_data: data,
      },
      freeze: true,
      freeze_message: __("Testing S3 Connection..."),
      callback: (r) => {
        // frappe.hide_message();
        console.log("Response from test_s3_connection:", r);
        if (r.exc) {
          // Error handling
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message:
              __("Failed to connect to S3: ") +
              __(r.exc_msg || "Unknown error"),
          });
          return;
        }

        try {
          // Check if response exists and has the expected structure
          if (r.message) {
            if (r.message.success) {
              frappe.msgprint({
                title: __("Connection Successful"),
                indicator: "green",
                message: __(r.message.message || "Connected successfully"),
              });
            } else {
              frappe.msgprint({
                title: __("Connection Failed"),
                indicator: "red",
                message: __(r.message.message || "Connection test failed"),
              });
            }
          } else {
            // Handle empty response
            frappe.msgprint({
              title: __("Connection Test"),
              indicator: "orange",
              message: __("Received empty response from server"),
            });
          }
        } catch (e) {
          // Handle any unexpected errors in callback processing
          frappe.msgprint({
            title: __("Error"),
            indicator: "red",
            message: __("Error processing server response: ") + e.message,
          });
        }
      },
    });
  },
});
