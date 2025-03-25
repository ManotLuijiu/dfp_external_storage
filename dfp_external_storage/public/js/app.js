// import './api';
// import './file_uploader'

const class_external_storage_icon = "dfp-storage-external-icon";

// Modify icons
function get_storage_icon(storage_type) {
  let icon_html = "";

  switch (storage_type) {
    case "AWS S3":
      icon_html = `<i class="fa-brands fa-aws ${class_external_storage_icon}"></i>`;
      break;
    case "Google Drive":
      icon_html = `<i class="fa-brands fa-google-drive ${class_external_storage_icon}"></i>`;
      break;
    case "OneDrive":
      icon_html = `<i class="fa-brands fa-microsoft ${class_external_storage_icon}"></i>`;
      break;
    case "Dropbox":
      icon_html = `<i class="fa-brands fa-dropbox ${class_external_storage_icon}"></i>`;
      break;
    default:
      // Fallback to cloud icon
      icon_html = `<i class="fa fa-cloud-upload ${class_external_storage_icon}"></i>`;
  }

  return icon_html;
}

function dfp_s3_icon(storage_type, title = "") {
  let $icon = $(get_storage_icon(storage_type));
  if (title) {
    $icon.attr("title", title);
  }
  return $icon;
}

// function dfp_s3_icon(title = "") {
//   let $icon = $(
//     `<i class="fa fa-cloud-upload ${class_external_storage_icon}"></i>`
//   );
//   if (title) {
//     $icon.attr("title", title);
//   }
//   return $icon;
// }

// Overrides for view FileView (Frappe file browser)
frappe.views.FileView = class DFPExternalStorageFileView extends (
  frappe.views.FileView
) {
  setup_defaults() {
    this._dfp_external_storages = [];
    return super.setup_defaults().then(() => {
      frappe.db
        .get_list("DFP External Storage", { fields: ["name", "title"] })
        .then((data) => (this._dfp_external_storages = data));
    });
  }

  _dfp_s3_title(dfp_external_storage) {
    let s3 = this._dfp_external_storages.filter(
      (i) => i.name == dfp_external_storage
    );
    return s3.length ? s3[0].title : __("No external storage name found :(");
  }

  // Add helper method to get storage type
  _get_storage_type(storage_id) {
    let storage = this._dfp_external_storages.find(
      (s) => s.name === storage_id
    );
    return storage ? storage.type : "AWS S3";
  }

  prepare_datum(d) {
    d = super.prepare_datum(d);
    if (d.dfp_external_storage_s3_key && d.dfp_external_storage) {
      let title = this._dfp_s3_title(d.dfp_external_storage);
      let storage_type = this._get_storage_type(d.dfp_external_storage);
      d.subject_html += dfp_s3_icon(storage_type, title).prop("outerHTML");
    }
    return d;
  }

  render_grid_view() {
    super.render_grid_view();
    let $file_grid = $(".file-grid");
    this.data.forEach((file) => {
      if (file.dfp_external_storage_s3_key && file.dfp_external_storage) {
        let $file = $file_grid.find(`[data-name="${file.name}"]`);
        let title = this._dfp_s3_title(file.dfp_external_storage);
        // $file.append(dfp_s3_icon(title));
        let storage_type = this._get_storage_type(file.dfp_external_storage);
        insertAnimatedIcon($file, dfp_s3_icon(storage_type, title));
      }
    });
  }
};

// File doc override
frappe.ui.form.on("File", {
  refresh: function (frm) {
    let $title_area = frm.$wrapper[0].page.$title_area;
    $title_area.find(`.${class_external_storage_icon}`).remove();
    if (frm.doc.dfp_external_storage_s3_key) {
      // $title_area.prepend(dfp_s3_icon());
      let storage_type = frm.doc.dfp_external_storage_type || "AWS S3";
      insertAnimatedIcon(
        $title_area,
        dfp_s3_icon(storage_type, frm.doc.dfp_external_storage)
      );
    }
  },
});

// Listing files overrides
frappe.listview_settings["File"] = {
  add_fields: ["dfp_external_storage_s3_key"],
};

// Helper function to ensure animation triggers when dynamically adding icons
function insertAnimatedIcon($container, $icon) {
  // Force a reflow to ensure the animation triggers properly
  $container.append($icon);
  void $icon[0].offsetWidth; // This triggers a reflow
  $icon.addClass("animate-in");
}
