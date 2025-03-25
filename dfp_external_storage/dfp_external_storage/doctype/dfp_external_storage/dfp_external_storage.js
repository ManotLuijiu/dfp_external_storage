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
    } else if (frm.doc.type === "OneDrive") {
      // Add OneDrive authentication button
      setup_onedrive_auth(frm);
    } else if (frm.doc.type === "Dropbox") {
      setup_dropbox_auth(frm);
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
    } else if (frm.doc.type === "OneDrive") {
      frm.events.test_onedrive_connection(frm);
    } else if (frm.doc.type === "Dropbox") {
      test_dropbox_connection(frm);
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

  test_google_drive_connection: function (frm) {
    // Validate required fields
    if (!frm.doc.google_client_id || !frm.doc.google_folder_id) {
      frappe.msgprint({
        title: __("Missing Information"),
        indicator: "red",
        message: __(
          "Client ID and Folder ID are required to test the connection."
        ),
      });
      return;
    }

    frappe.show_alert(__("Testing Google Drive Connection..."));

    frappe.call({
      method:
        "dfp_external_storage.gdrive_integration.test_google_drive_connection",
      args: {
        doc_name: frm.doc.name,
      },
      freeze: true,
      freeze_message: __("Testing Google Drive Connection..."),
      callback: (r) => {
        console.log("Response from test_google_drive_connection:", r);
        if (r.exc) {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message:
              __("Failed to connect to Google Drive: ") +
              __(r.exc_msg || "Unknown error"),
          });
        } else if (r.message && r.message.success) {
          frappe.msgprint({
            title: __("Connection Successful"),
            indicator: "green",
            message: __(
              r.message.message || "Successfully connected to Google Drive."
            ),
          });
        } else {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message: __(
              r.message
                ? r.message.message
                : "Unknown error connecting to Google Drive."
            ),
          });
        }
      },
    });
  },

  test_onedrive_connection: function (frm) {
    // Validate required fields
    if (!frm.doc.onedrive_client_id || !frm.doc.onedrive_folder_id) {
      frappe.msgprint({
        title: __("Missing Information"),
        indicator: "red",
        message: __(
          "Client ID and Folder ID are required to test the connection."
        ),
      });
      return;
    }

    frappe.show_message(__("Testing OneDrive Connection..."));

    frappe.call({
      method:
        "dfp_external_storage.onedrive_integration.test_onedrive_connection",
      args: {
        doc_name: frm.doc.name,
      },
      freeze: true,
      freeze_message: __("Testing OneDrive Connection..."),
      callback: (r) => {
        frappe.hide_message();
        if (r.exc) {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message:
              __("Failed to connect to OneDrive: ") +
              __(r.exc_msg || "Unknown error"),
          });
        } else if (r.message && r.message.success) {
          frappe.msgprint({
            title: __("Connection Successful"),
            indicator: "green",
            message: __(
              r.message.message || "Successfully connected to OneDrive."
            ),
          });
        } else {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message: __(
              r.message
                ? r.message.message
                : "Unknown error connecting to OneDrive."
            ),
          });
        }
      },
    });
  },

  test_dropbox_connection: function (frm) {
    // Validate required fields
    if (!frm.doc.dropbox_app_key || !frm.doc.dropbox_folder_path) {
      frappe.msgprint({
        title: __("Missing Information"),
        indicator: "red",
        message: __(
          "App Key and Folder Path are required to test the connection."
        ),
      });
      return;
    }
    frappe.show_message(__("Testing Dropbox Connection..."));

    frappe.call({
      method:
        "dfp_external_storage.dropbox_integration.test_dropbox_connection",
      args: {
        doc_name: frm.doc.name,
      },
      freeze: true,
      freeze_message: __("Testing Dropbox Connection..."),
      callback: (r) => {
        frappe.hide_message();
        if (r.exc) {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message:
              __("Failed to connect to Dropbox: ") +
              __(r.exc_msg || "Unknown error"),
          });
        } else if (r.message && r.message.success) {
          frappe.msgprint({
            title: __("Connection Successful"),
            indicator: "green",
            message: __(
              r.message.message || "Successfully connected to Dropbox."
            ),
          });
        } else {
          frappe.msgprint({
            title: __("Connection Failed"),
            indicator: "red",
            message: __(
              r.message
                ? r.message.message
                : "Unknown error connecting to Dropbox."
            ),
          });
        }
      },
    });
  },
});

// Google Drive Authentication functions
function setup_google_drive_auth(frm) {
  // First check if we already have credentials in the session
  frappe.call({
    method: "dfp_external_storage.gdrive_integration.get_auth_credentials",
    callback: (r) => {
      if (r.message) {
        // We have credentials, show button to apply them
        setup_apply_credentials_button(frm, r.message);
      } else {
        // No credentials, show authenticate button
        setup_auth_button(frm);
      }
    },
  });
}

function setup_auth_button(frm) {
  $("#google-auth-btn")
    .off("click")
    .on("click", function () {
      // Client ID and secret are required
      if (!frm.doc.google_client_id || !frm.doc.google_client_secret) {
        frappe.msgprint({
          title: __("Missing Information"),
          indicator: "red",
          message: __(
            "Client ID and Client Secret are required for authentication."
          ),
        });
        return;
      }

      frappe.call({
        method:
          "dfp_external_storage.gdrive_integration.initiate_google_drive_auth",
        args: {
          doc_name: frm.doc.name,
          client_id: frm.doc.google_client_id,
          client_secret: frm.doc.google_client_secret,
        },
        callback: (r) => {
          if (r.message && r.message.success) {
            // Open the auth URL in a new window
            const authWindow = window.open(
              r.message.auth_url,
              "GoogleDriveAuth",
              "width=600,height=700,location=yes,resizable=yes,scrollbars=yes,status=yes"
            );

            // Add message about the popup
            frappe.show_alert(
              {
                message: __(
                  "Google authentication window opened. Please complete the authentication process in the new window."
                ),
                indicator: "blue",
              },
              10
            );

            // Check if window was blocked
            if (
              !authWindow ||
              authWindow.closed ||
              typeof authWindow.closed === "undefined"
            ) {
              frappe.msgprint({
                title: __("Popup Blocked"),
                indicator: "red",
                message: __(
                  "The authentication popup was blocked. Please allow popups for this site and try again."
                ),
              });
            }
          } else {
            frappe.msgprint({
              title: __("Authentication Failed"),
              indicator: "red",
              message: __(
                r.message
                  ? r.message.error
                  : "Failed to initiate Google Drive authentication."
              ),
            });
          }
        },
      });
    });
}

function setup_apply_credentials_button(frm, credentials) {
  // Replace the auth button with an apply credentials button
  $(".google-auth-button").html(
    `<button class="btn btn-primary btn-sm" id="apply-credentials-btn">Apply Authentication</button>`
  );

  $("#apply-credentials-btn")
    .off("click")
    .on("click", function () {
      // Set the refresh token in the form
      frm.set_value("google_refresh_token", credentials.refresh_token);

      frappe.show_alert(
        {
          message: __(
            "Authentication credentials applied. You can now save the document."
          ),
          indicator: "green",
        },
        5
      );

      // Replace with re-authenticate button
      $(".google-auth-button").html(
        `<button class="btn btn-default btn-sm" id="google-auth-btn">Re-authenticate with Google Drive</button>`
      );
      setup_auth_button(frm);
    });
}

// OneDrive integration code for DFP External Storage JS
// OneDrive Authentication functions
function setup_onedrive_auth(frm) {
  // First check if we already have credentials in the session
  frappe.call({
    method: "dfp_external_storage.onedrive_integration.get_auth_credentials",
    callback: (r) => {
      if (r.message) {
        // We have credentials, show button to apply them
        setup_onedrive_apply_credentials_button(frm, r.message);
      } else {
        // No credentials, show authenticate button
        setup_onedrive_auth_button(frm);
      }
    },
  });
}

function setup_onedrive_auth_button(frm) {
  $("#onedrive-auth-btn")
    .off("click")
    .on("click", function () {
      // Client ID and secret are required
      if (!frm.doc.onedrive_client_id || !frm.doc.onedrive_client_secret) {
        frappe.msgprint({
          title: __("Missing Information"),
          indicator: "red",
          message: __(
            "Client ID and Client Secret are required for authentication."
          ),
        });
        return;
      }

      frappe.call({
        method:
          "dfp_external_storage.onedrive_integration.initiate_onedrive_auth",
        args: {
          doc_name: frm.doc.name,
          client_id: frm.doc.onedrive_client_id,
          client_secret: frm.doc.onedrive_client_secret,
          tenant: frm.doc.onedrive_tenant || "common",
        },
        callback: (r) => {
          if (r.message && r.message.success) {
            // Open the auth URL in a new window
            const authWindow = window.open(
              r.message.auth_url,
              "OneDriveAuth",
              "width=600,height=700,location=yes,resizable=yes,scrollbars=yes,status=yes"
            );

            // Add message about the popup
            frappe.show_alert(
              {
                message: __(
                  "OneDrive authentication window opened. Please complete the authentication process in the new window."
                ),
                indicator: "blue",
              },
              10
            );

            // Check if window was blocked
            if (
              !authWindow ||
              authWindow.closed ||
              typeof authWindow.closed === "undefined"
            ) {
              frappe.msgprint({
                title: __("Popup Blocked"),
                indicator: "red",
                message: __(
                  "The authentication popup was blocked. Please allow popups for this site and try again."
                ),
              });
            }
          } else {
            frappe.msgprint({
              title: __("Authentication Failed"),
              indicator: "red",
              message: __(
                r.message
                  ? r.message.error
                  : "Failed to initiate OneDrive authentication."
              ),
            });
          }
        },
      });
    });
}

function setup_onedrive_apply_credentials_button(frm, credentials) {
  // Replace the auth button with an apply credentials button
  $(".onedrive-auth-button").html(
    `<button class="btn btn-primary btn-sm" id="apply-onedrive-credentials-btn">Apply Authentication</button>`
  );

  $("#apply-onedrive-credentials-btn")
    .off("click")
    .on("click", function () {
      // Set the refresh token in the form
      frm.set_value("onedrive_refresh_token", credentials.refresh_token);

      frappe.show_alert(
        {
          message: __(
            "OneDrive authentication credentials applied. You can now save the document."
          ),
          indicator: "green",
        },
        5
      );

      // Replace with re-authenticate button
      $(".onedrive-auth-button").html(
        `<button class="btn btn-default btn-sm" id="onedrive-auth-btn">Re-authenticate with OneDrive</button>`
      );
      setup_onedrive_auth_button(frm);
    });
}

// Dropbox Authentication functions
function setup_dropbox_auth(frm) {
  // First check if we already have credentials in the session
  frappe.call({
    method: "dfp_external_storage.dropbox_integration.get_auth_credentials",
    callback: (r) => {
      if (r.message) {
        // We have credentials, show button to apply them
        setup_dropbox_apply_credentials_button(frm, r.message);
      } else {
        // No credentials, show authenticate button
        setup_dropbox_auth_button(frm);
      }
    },
  });
}

function setup_dropbox_auth_button(frm) {
  $("#dropbox-auth-btn")
    .off("click")
    .on("click", function () {
      // App key and secret are required
      if (!frm.doc.dropbox_app_key || !frm.doc.dropbox_app_secret) {
        frappe.msgprint({
          title: __("Missing Information"),
          indicator: "red",
          message: __(
            "App Key and App Secret are required for authentication."
          ),
        });
        return;
      }

      frappe.call({
        method:
          "dfp_external_storage.dropbox_integration.initiate_dropbox_auth",
        args: {
          doc_name: frm.doc.name,
          app_key: frm.doc.dropbox_app_key,
          app_secret: frm.doc.dropbox_app_secret,
        },
        callback: (r) => {
          if (r.message && r.message.success) {
            // Open the auth URL in a new window
            const authWindow = window.open(
              r.message.auth_url,
              "DropboxAuth",
              "width=600,height=700,location=yes,resizable=yes,scrollbars=yes,status=yes"
            );

            // Add message about the popup
            frappe.show_alert(
              {
                message: __(
                  "Dropbox authentication window opened. Please complete the authentication process in the new window."
                ),
                indicator: "blue",
              },
              10
            );

            // Check if window was blocked
            if (
              !authWindow ||
              authWindow.closed ||
              typeof authWindow.closed === "undefined"
            ) {
              frappe.msgprint({
                title: __("Popup Blocked"),
                indicator: "red",
                message: __(
                  "The authentication popup was blocked. Please allow popups for this site and try again."
                ),
              });
            }
          } else {
            frappe.msgprint({
              title: __("Authentication Failed"),
              indicator: "red",
              message: __(
                r.message
                  ? r.message.error
                  : "Failed to initiate Dropbox authentication."
              ),
            });
          }
        },
      });
    });
}

function setup_dropbox_apply_credentials_button(frm, credentials) {
  // Replace the auth button with an apply credentials button
  $(".dropbox-auth-button").html(
    `<button class="btn btn-primary btn-sm" id="apply-dropbox-credentials-btn">Apply Authentication</button>`
  );

  $("#apply-dropbox-credentials-btn")
    .off("click")
    .on("click", function () {
      // Set the refresh token in the form
      frm.set_value("dropbox_refresh_token", credentials.refresh_token);

      frappe.show_alert(
        {
          message: __(
            "Dropbox authentication credentials applied. You can now save the document."
          ),
          indicator: "green",
        },
        5
      );

      // Replace with re-authenticate button
      $(".dropbox-auth-button").html(
        `<button class="btn btn-default btn-sm" id="dropbox-auth-btn">Re-authenticate with Dropbox</button>`
      );
      setup_dropbox_auth_button(frm);
    });
}
