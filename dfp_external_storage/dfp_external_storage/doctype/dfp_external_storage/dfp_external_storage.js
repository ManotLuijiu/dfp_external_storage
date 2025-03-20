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

    // Add Test Connection button
    frm
      .add_custom_button(__("Test S3 Connection"), function () {
        frm.events.test_s3_connection(frm);
      })
      .addClass("btn-primary");

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

  test_s3_connection: function (frm) {
    frappe.show_message(__("Testing S3 Connection..."));

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
        frappe.hide_message();
        if (r.exc) {
          // Error handling
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message:
              __("Failed to connect to S3: ") +
              __(r.exc_msg || "Unknown error"),
          });
        } else if (r.message.success) {
          // Success message
          frappe.msgprint({
            title: __("Connection Successful"),
            indicator: "green",
            message: __(r.message.message),
          });
        } else {
          // Failed but with a message
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message: __(r.message.message),
          });
        }
      },
    });
  },
});
