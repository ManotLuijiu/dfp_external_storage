frappe.pages['dfp-s3-bucket-list'].on_page_load = (wrapper) => {
	const dfp_s3_bucket_list = new DFPS3BucketList(wrapper)
	$(wrapper).bind('show', () => {
		dfp_s3_bucket_list.show()
	})
	window.dfp_s3_bucket_list = dfp_s3_bucket_list
	window.fileSizeToHumansMode = dfp_s3_bucket_list.fileSizeToHumansMode
}

class DFPS3BucketList {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('S3 bucket files'),
			single_column: true,
		})


		this.page.main.addClass('frappe-card')
		this.page.body.append('<div class="dfp-content-main"></div>')
		this.$content = $(this.page.body).find('.dfp-content-main')

		// Add diagnostic button in the page header
		this.page.set_primary_action(__('Diagnose Connection'), () => {
			this.diagnoseConnection()
		}, 'octicon octicon-pulse')

		this.make_filters()
		this.refresh_files = frappe.utils.throttle(this.refresh_files.bind(this), 1000)


		frappe.router.on('change', () => {
			if (frappe.get_route()[0] === 'dfp-s3-bucket-list') {
				// debugger
				if (this.storage.get_value() !== frappe.get_route()[1]) {
					this.storage.set_value(frappe.get_route()[1])
				}
				this.refresh_files()
			}
		})
	}

	// Add new diagnostic method
	diagnoseConnection() {
        const storage_name = this.storage.get_value();
        if (!storage_name) {
            frappe.throw(__('Please select a storage connection first'));
            return;
        }

        frappe.show_message(__('Diagnosing connection...'));

        frappe.call({
            method: 'dfp_external_storage.dfp_external_storage.page.dfp_s3_bucket_list.dfp_s3_bucket_list.diagnose_storage_connection',
            args: {
                storage_name: storage_name
            },
            callback: (r) => {
                frappe.hide_message();
                if (r.exc) {
                    // Error handling is done by frappe
                    return;
                }
                // Success handling is done by msgprint in Python
            },
            error: (err) => {
                frappe.hide_message();
                frappe.throw(__('Connection diagnosis failed: ') + err.message);
            }
        });
    }

	make_filters() {
		console.log('frappe.get_route()', frappe.get_route())
		this.storage = this.page.add_field({
			label: __('DFP External Storage'),
			fieldname: 'storage',
			fieldtype: 'Link',
			options: 'DFP External Storage',
			// TODO: auto select the first one available
			// default: null,
			default: frappe.get_route().length > 1 ? frappe.get_route()[1] : null,
			// default: 'DFP.ES.dfp-external-storage.230710.01',
			reqd: 1,
			change: () => {
				// debugger
				frappe.set_route('dfp-s3-bucket-list', this.storage.get_value())
				// if (this.storage.get_value() !== frappe.get_route()[1]) {
				// 	this.storage.set_value(frappe.get_route()[1])
				// }
				// debugger
				// this.refresh_files()
				// debugger
			},
		})
		// console.log(this.storage.get_value())
		// this.storage.refresh()
		// console.log(this.storage.get_value())
		// debugger
		this.template = this.page.add_field({
			label: __('View mode'),
			fieldname: 'template',
			fieldtype: 'Select',
			options: [
				{ label: 'List', value: 'list' },
				// TODO: Create grid view ¿?
				// { label: 'Grid', value: 'grid' },
			],
			default: 'list',
			reqd: 1,
			// change: () => this.refresh_files(),
		})
		this.file_type = this.page.add_field({
			label: __('File type'),
			fieldname: 'type',
			fieldtype: 'Select',
			options: [
				{ label: 'All files', value: 'all' },
				// TODO: set file filters!
				// { label: 'Images', value: 'image' },
				// { label: 'Videos', value: 'video' },
				// { label: 'PDFs', value: 'pdf' },
			],
			default: 'all',
			change: () => this.refresh_files(),
		})
		this.auto_refresh = this.page.add_field({
			label: __('Auto Refresh'),
			fieldname: 'auto_refresh',
			fieldtype: 'Check',
			default: 0,
			change: () => {
				if (this.auto_refresh.get_value()) {
					this.refresh_files()
				}
			},
		})
	}

	show() {
		this.refresh_files()
		// this.update_scheduler_status()
	}

	// update_scheduler_status() {
	// 	frappe.call({
	// 		method: 'frappe.core.page.background_jobs.background_jobs.get_scheduler_status',
	// 		callback: (r) => {
	// 			let { status } = r.message;
	// 			if (status === 'active') {
	// 				this.page.set_indicator(__('Scheduler: Active'), 'green')
	// 			} else {
	// 				this.page.set_indicator(__('Scheduler: Inactive'), 'red')
	// 			}
	// 		},
	// 	})
	// }

	refresh_files() {
		let template;
		try {
			template = this.template.get_value();
			if (!template) {
				frappe.throw(__('Template is required'));
			}
		} catch (e) {
			frappe.throw(__('Error getting template value: ') + e.message);
		}
		console.log('Template value:', this.template.get_value());

		// let template = this.template.get_value()
		// TODO: why is not working .get_value()??
		// let storage = this.storage.get_value()
		// let storage = this.storage.value
		// Get storage from route or fallback
		let storage = frappe.get_route()[1]
		if (!storage) {
			frappe.throw(__('Storage parameter is required'));
		}
		console.log('Storage route:', frappe.get_route()[1]);

		// Get file type with error handling
		let file_type;
		try {
			file_type = this.file_type.get_value();
		} catch (e) {
			frappe.throw(__('Error getting file type: ') + e.message)
		}
		console.log('File type:', this.file_type.get_value());
		// let file_type = this.file_type.get_value()
		// let test = this.page.get_form_values()
		let args = { storage, template, file_type }

		// Show loading message
		this.page.add_inner_message(__('Refreshing...'))

		frappe.call({ method: 'dfp_external_storage.dfp_external_storage.page.dfp_s3_bucket_list.dfp_s3_bucket_list.get_info', args, callback: (res) => {
				this.page.add_inner_message('');

				// Check if response is valid
				if (!res || !Array.isArray(res.message)) {
					frappe.throw(__('Invalid response from server'));
					return;
				}

				try {
					// Render template
					this.$content.html(
						frappe.render_template(template, {
							files: res.message || [],
						})
					);
				} catch (e) {
					frappe.throw(__('Error rendering template: ') + e.message);
					return;
				}
				// this.$content.html(
				// 	frappe.render_template(template, {
				// 		files: res.message || [],
				// 	})
				// )

				// Handle auto refresh
				let auto_refresh;
				try {
					auto_refresh = this.auto_refresh.get_value();
				} catch (e) {
					console.error('Error getting auto_refresh value:', e);
					return;
				}
				// let auto_refresh = this.auto_refresh.get_value()

				// if (frappe.get_route()[0] === 'dfp-s3-bucket-list' && auto_refresh) {
				if (frappe.get_route()[0] === 'dfp-s3-bucket-list' && auto_refresh) {
					setTimeout(() => this.refresh_files(), 2000)
				}
			},
			error: (err) => {
				this.page.add_inner_message('');
				frappe.throw(__('Error fetching files: ') + err.message);
			}
		});
	}

	fileSizeToHumansMode(size) {
		const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
		let i = 0
		while (size >= 1024 && i < units.length - 1) {
			size /= 1024
			i++
		}
		return `${size.toFixed(1)} ${units[i]}`
	}
}
