# DFP External Storage

> **😊 ขอบคุณ! / Thanks!**
>
> หากคุณพบว่าโค้ดนี้มีประโยชน์ โปรดช่วยผม (<https://github.com/sponsors/developmentforpeople>) ในการปรับปรุงและพัฒนาต่อไป ขอบคุณมากๆ สำหรับความช่วยเหลือของคุณ 🫶!
>
> If you find this code useful, please help me (<https://github.com/sponsors/developmentforpeople>) to keep it updated, improved and safe. Thank you very much for your help 🫶!

_Read this in: [🇬🇧 English](#english-version) | [🇹🇭 ภาษาไทย](#thai-version--ภาษาไทย)
_

---

## English Version

Simplest cloud file management for Frappe / ERPNext. S3 compatible external bucket can be assigned per Frappe folder, allowing you to fine-tune the location of your Frappe / ERPNext "File"s: within local filesystem or to external S3 bucket.

_This repository is a fork of the [original DFP External Storage](https://github.com/developmentforpeople/dfp_external_storage) project with additional enhancements for easier installation and Thai language support._

[![Frappe files within S3 buckets](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/e762a286-b2c7-4a9b-a7e3-486b9a0892d6)](https://www.youtube.com/embed/2uTnWZxhtug)

### Examples / Use cases

#### All Frappe / ERPNext files into external S3 compatible bucket

[upload_frappe_erpnext_files_s3_compatible_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/68592d26-4391-45fc-bd75-d4d5f06ce899)

#### Move files / objects from S3 compatible bucket to another S3 compatible bucket (between buckets in same or different connection)

[move_objects_from_one_s3_compatible_bucket_to_another.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/9c4d7197-d19e-422e-85a9-8af7725014f0)

#### Move files / objects from S3 compatible bucket to local file system

[move_objects_from_s3_compatible_to_local_filesystem.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/2d4eccf1-f7e2-4c89-9694-95ec36b6856d)

#### Move files in local filesystem to S3 compatible bucket

[move_local_files_to_s3_compatible_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/6a19d3b6-48c6-46a1-a08d-29d3555b4419)

#### Per file examples

[move_file_from_s3_compatible_bucket_to_different_one_then_to_local_file.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/1a4f216a-a6b4-4728-a27e-efdf4cbcf983)

#### List all remote files in bucket

Shows all files in bucket, even the ones not in Frappe File doctype.

[list_files_in_remote_s3_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/fbd38418-686e-45b4-b23b-048bed4d1143)

#### Customizable

Choose the best setup for you: S3 only for all site files or specified folders, use S3 / Minio presigned urls, cache or not small files, etc.

![Settings](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/0ad2f24b-d37d-4882-80c4-c1e77a74f666)

### Requirements

- Frappe version >= 14
- minio Python package
- boto3 Python package (version >= 1.34.0)

### Installation

#### Option 1: Standard Installation

```bash
# Get the app
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git

# Install dependencies
pip install minio boto3>=1.34.0

# Install the app on your site
bench --site your-site.com install-app dfp_external_storage
```

#### Option 2: Automated Installation (with dependency check)

```bash
# Get the app
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git

# Run the installation helper script
bench --site your-site.com execute dfp_external_storage/install.py

# Install the app on your site
bench --site your-site.com install-app dfp_external_storage
```

### Troubleshooting Installation Issues

If you encounter errors about duplicate entries during installation, it's likely due to remnants of a previous installation. You can use the cleanup script:

```bash
# Clean up any previous installation data
bench --site your-site.com execute dfp_external_storage/app_cleanup.py --args '["DFP External Storage"]'

# Then try installing again
bench --site your-site.com install-app dfp_external_storage
```

### Functionalities

- S3 bucket can be defined per folder/s. If "Home" folder defined, all Frappe / ERPNext files will use that S3 bucket.
- Files accesible with custom URLs: /file/[File ID]/[file name.extension]
- Frappe / ERPNext private/public functionality is preserved for external files. If an external private file is loaded not having access a not found page will be showed.
- External Storages can be write disabled, but files will be visible yet.
- Bulk file relocation (upload and download). You can filter by local S3 bucket/local filesystem and then change all those files to a different S3 bucket or to local filesystem. All files are "moved" without load them fully in memory optimizing large ones transfer.
- Small icon allows you visualize if file is within an S3 bucket.
- Same file upload (same file hash) will reuse existent S3 key and is not reuploaded. Same functionality as Frappe has with local files.
- Choosed S3 bucket file listing tool.
- S3 bucket can not be deleted if has "File"s assigned / within it.
- If bucket is not accesible file will be uploaded to local filesystem.
- Stream data in chunks to and from S3 without reading whole files into memory (thanks to [Khoran](https://github.com/khoran)
- List all remote objects in bucket (includes too the ones not uploaded trough Frappe)
- Support for S3 / Minio presigned urls: allowing video streaming capabilities and other S3 functionalities.
- Presigned url can be used for all files in defined folders but defined by mimetype.
- Files are now streamed by default.
- Extended settings per External Storage doc:
  - Cache only files smaller than
  - Cache for x seconds
  - Stream buffer size
  - Presigned url activation
  - Presigned url only for mimetypes defined
  - Presigned url expiration
  - Use S3 file size instead of saved on Frappe File (needed for files > 2GB)
- ... maybe I am forgetting something ;)

### Flow options

- No S3 external storages defined
- or S3 external storages defined but not assigned to folders:
  - All uploaded files are saved in local filesystem
- One S3 external storage assigned to "Attachments" folder:
  - Only files uploaded to that folder will be use that S3 bucket
- One S3 external storage assigned to "Home" folder:
  - All files uploaded to Frappe will be located within that bucket. Except the files uploaded to "Attachments" that will use the above defined bucket

### File actions available

- If a "File" has an "DFP External Storage" assigned.
  - If changed to a different "DFP External Storage" file will be:
    - "downloaded" from previous bucket > "uploaded" to new bucket > "deleted" from previous bucket.
  - If leaved empty, file will be "downloaded" to local filesystem > "deleted" from bucket.
- If a "File" has no "DFP External Storage" assigned, so it is in local filesystem:
  - If assigned a "DFP External Storage", file will be:
    - "uploaded" to that bucket > "deleted" from filesystem

### Setup or try it locally

#### Install Frappe 14

Follow all steps for your OS within official guide: [https://frappeframework.com/docs/v14/user/en/installation](https://frappeframework.com/docs/v14/user/en/installation).

#### Create your personal "frappe-bench" environment (customizable folder name)

Into your home folder:

```bash
cd ~
bench init frappe-bench
```

#### Install "dfp_external_storage" app

```bash
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git
```

#### Create a new site with "dfp_external_storage" app installed on it

```bash
cd ~/frappe-bench
bench new-site dfp_external_storage_site.localhost --install-app dfp_external_storage
```

#### Initialize servers to get site running

```bash
cd ~/frappe-bench
bench start
```

#### Create one or more "DFP External Storage"s

Add one or more S3 bucket and, this is the most important step, assign "Home" folder to it. This makes all files uploaded to Frappe / ERPNext being uploaded to that bucket.

You can select a different folder and only those files will be uploaded, or select different buckets for different folders, your imagination is your limit!! :D

#### Stream data to and from S3 without reading whole files into memory

Option is valuable when working with large files.

For uploading content from a local file, usage would look like:

```python
file_doc = frappe.get_doc({
    "doctype":"File",
    "is_private":True,
    "file_name": "file name here"
})
file_doc.dfp_external_storage_upload_file(filepath)
file_doc.save()
```

To download content to a local file:

```python
file_doc = frappe.get_doc("File",doc_name)
file_doc.dfp-external_storage_download_to_file("/path/to/local/file")
```

To read remote file directly via a proxy object:

```python
file_doc = frappe.get_doc("File",doc_name)

#read zip file table of contents without downloading the whole zip file
with zipfile.ZipFile(file_doc.dfp_external_storage_file_proxy()) as z:
  for zipinfo in z.infolist():
     print(f"{zipinfo.filename}")

```

---

## Thai Version / ภาษาไทย

เป็นการจัดการไฟล์บนคลาวด์ที่ง่ายที่สุดสำหรับ Frappe / ERPNext บัคเก็ต S3 ที่รองรับภายนอกสามารถกำหนดตามโฟลเดอร์ของ Frappe ได้ ทำให้คุณสามารถปรับแต่งตำแหน่งของไฟล์ Frappe / ERPNext ได้อย่างละเอียด: ไม่ว่าจะอยู่ภายในระบบไฟล์ภายในเครื่องหรือบัคเก็ต S3 ภายนอก

_รีพอสิทอรีนี้เป็นการ fork มาจาก[โปรเจกต์ DFP External Storage ต้นฉบับ](https://github.com/developmentforpeople/dfp_external_storage) พร้อมการปรับปรุงเพิ่มเติมเพื่อให้การติดตั้งง่ายขึ้นและรองรับภาษาไทย_

[![ไฟล์ Frappe ในบัคเก็ต S3](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/e762a286-b2c7-4a9b-a7e3-486b9a0892d6)](https://www.youtube.com/embed/2uTnWZxhtug)

### ตัวอย่างการใช้งาน

#### ไฟล์ Frappe / ERPNext ทั้งหมดในบัคเก็ต S3 ภายนอกที่รองรับ

[upload_frappe_erpnext_files_s3_compatible_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/68592d26-4391-45fc-bd75-d4d5f06ce899)

#### ย้ายไฟล์/วัตถุจากบัคเก็ต S3 ที่รองรับไปยังบัคเก็ต S3 อื่นที่รองรับ (ระหว่างบัคเก็ตในการเชื่อมต่อเดียวกันหรือต่างกัน)

[move_objects_from_one_s3_compatible_bucket_to_another.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/9c4d7197-d19e-422e-85a9-8af7725014f0)

#### ย้ายไฟล์/วัตถุจากบัคเก็ต S3 ที่รองรับไปยังระบบไฟล์ภายในเครื่อง

[move_objects_from_s3_compatible_to_local_filesystem.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/2d4eccf1-f7e2-4c89-9694-95ec36b6856d)

#### ย้ายไฟล์ในระบบไฟล์ภายในเครื่องไปยังบัคเก็ต S3 ที่รองรับ

[move_local_files_to_s3_compatible_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/6a19d3b6-48c6-46a1-a08d-29d3555b4419)

#### ตัวอย่างรายไฟล์

[move_file_from_s3_compatible_bucket_to_different_one_then_to_local_file.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/1a4f216a-a6b4-4728-a27e-efdf4cbcf983)

#### แสดงไฟล์ทั้งหมดในบัคเก็ตระยะไกล

แสดงไฟล์ทั้งหมดในบัคเก็ต แม้กระทั่งไฟล์ที่ไม่อยู่ใน Frappe File doctype

[list_files_in_remote_s3_bucket.webm](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/fbd38418-686e-45b4-b23b-048bed4d1143)

#### ปรับแต่งได้

เลือกการตั้งค่าที่ดีที่สุดสำหรับคุณ: S3 เท่านั้นสำหรับไฟล์ไซต์ทั้งหมดหรือโฟลเดอร์ที่ระบุ, ใช้ URL ที่ลงนามล่วงหน้าของ S3 / Minio, แคชหรือไม่แคชไฟล์ขนาดเล็ก ฯลฯ

![การตั้งค่า](https://github.com/developmentforpeople/dfp_external_storage/assets/47140294/0ad2f24b-d37d-4882-80c4-c1e77a74f666)

### ความต้องการของระบบ

- Frappe เวอร์ชัน >= 14
- แพ็คเกจ Python ชื่อ minio
- แพ็คเกจ Python ชื่อ boto3 (เวอร์ชัน >= 1.34.0)

### การติดตั้ง

#### ตัวเลือกที่ 1: การติดตั้งมาตรฐาน

```bash
# รับแอป
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git

# ติดตั้งแพ็คเกจที่จำเป็น
pip install minio boto3>=1.34.0

# ติดตั้งแอปบนไซต์ของคุณ
bench --site your-site.com install-app dfp_external_storage
```

ในกรณีลืมติดตั้ง minio ก่อนติดตั้ง dfp_external_storage จะติดตั้งซ้ำไม่ได้ มันจะแสดง Error นี้

```bash
Installing dfp_external_storage...
An error occurred while installing dfp_external_storage: ('Module Def', 'DFP External Storage', IntegrityError(1062, "Duplicate entry 'DFP External Storage' for key 'PRIMARY'"))
```

ให้แก้ด้วยการรันโค้ดนี้ครับ

```bash
bench --site your-site console
```

เมื่อเข้ามาที่หน้า console แล้วให้คัดลอกโค้ดทั้งหมดนี้แล้ววางตรง console ได้เลยครับ แล้วกด Enter

```python
# First, get all doctypes in this module
doctypes = frappe.db.get_all("DocType", filters={"module": "DFP External Storage"}, fields=["name"])
print("DocTypes to delete:", doctypes)

# Delete each doctype
for dt in doctypes:
    print(f"Deleting DocType: {dt['name']}")
    try:
        # First delete any documents of this type
        if frappe.db.table_exists(f"tab{dt['name']}"):
            frappe.db.sql(f"DELETE FROM `tab{dt['name']}`")

        # Then delete the DocType itself
        frappe.delete_doc("DocType", dt['name'], force=True)
    except Exception as e:
        print(f"Error deleting {dt['name']}: {str(e)}")

# Delete any pages
pages = frappe.db.get_all("Page", filters={"module": "DFP External Storage"}, fields=["name"])
for page in pages:
    print(f"Deleting Page: {page['name']}")
    frappe.delete_doc("Page", page['name'], force=True)

# Delete the Module Def itself
print("Deleting Module Def: DFP External Storage")
if frappe.db.exists("Module Def", "DFP External Storage"):
    frappe.delete_doc("Module Def", "DFP External Storage", force=True)

# Commit the changes
frappe.db.commit()
print("Cleanup complete. You can now try installing the app again.")
```

เสร็จแล้วรันโค้ด

```python
exit()
```

เพื่อออกมาที่ bench ต่อไปให้รันคำสั่ง

```bash
bench --site your-site install-app dfp_external_storage
```

#### ตัวเลือกที่ 2: การติดตั้งอัตโนมัติ (พร้อมการตรวจสอบแพ็คเกจที่จำเป็น)

```bash
# รับแอป
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git

# เรียกใช้สคริปต์ช่วยติดตั้ง
bench --site your-site.com execute dfp_external_storage/install.py

# ติดตั้งแอปบนไซต์ของคุณ
bench --site your-site.com install-app dfp_external_storage
```

### การแก้ไขปัญหาการติดตั้ง

หากคุณพบข้อผิดพลาดเกี่ยวกับรายการซ้ำในระหว่างการติดตั้ง อาจเกิดจากซากของการติดตั้งก่อนหน้า คุณสามารถใช้สคริปต์ทำความสะอาดได้:

```bash
# ล้างข้อมูลการติดตั้งเดิม
bench --site your-site.com execute dfp_external_storage/app_cleanup.py --args '["DFP External Storage"]'

# จากนั้นลองติดตั้งอีกครั้ง
bench --site your-site.com install-app dfp_external_storage
```

### ฟังก์ชันการทำงาน

- สามารถกำหนด S3 bucket ต่อโฟลเดอร์ได้ หากกำหนดโฟลเดอร์ "Home" ไฟล์ Frappe / ERPNext ทั้งหมดจะใช้ S3 bucket นั้น
- ไฟล์สามารถเข้าถึงได้ด้วย URL แบบกำหนดเอง: /file/[File ID]/[file name.extension]
- ฟังก์ชันส่วนตัว/สาธารณะของ Frappe / ERPNext ยังคงถูกรักษาไว้สำหรับไฟล์ภายนอก หากมีการโหลดไฟล์ส่วนตัวภายนอกโดยไม่มีสิทธิ์เข้าถึง จะแสดงหน้า "ไม่พบ"
- พื้นที่จัดเก็บภายนอกสามารถปิดการเขียนได้ แต่ไฟล์ยังคงมองเห็นได้
- การย้ายไฟล์จำนวนมาก (อัปโหลดและดาวน์โหลด) คุณสามารถกรองตาม S3 bucket ภายใน/ระบบไฟล์ภายในและเปลี่ยนไฟล์ทั้งหมดเหล่านั้นไปยัง S3 bucket อื่นหรือไปยังระบบไฟล์ภายใน ไฟล์ทั้งหมดถูก "ย้าย" โดยไม่ต้องโหลดเข้าหน่วยความจำทั้งหมด เพื่อเพิ่มประสิทธิภาพการถ่ายโอนไฟล์ขนาดใหญ่
- ไอคอนขนาดเล็กช่วยให้คุณมองเห็นว่าไฟล์อยู่ภายใน S3 bucket หรือไม่
- การอัปโหลดไฟล์เดียวกัน (แฮชไฟล์เดียวกัน) จะใช้คีย์ S3 ที่มีอยู่และไม่ถูกอัปโหลดใหม่ ฟังก์ชันเดียวกับที่ Frappe มีกับไฟล์ภายใน
- เครื่องมือแสดงรายการไฟล์ S3 bucket ที่เลือก
- ไม่สามารถลบ S3 bucket ได้หากมี "ไฟล์" ที่กำหนดให้/อยู่ภายใน
- หากไม่สามารถเข้าถึง bucket ได้ ไฟล์จะถูกอัปโหลดไปยังระบบไฟล์ภายใน
- สตรีมข้อมูลเป็นชิ้นๆ ไปและมาจาก S3 โดยไม่ต้องอ่านไฟล์ทั้งหมดเข้าหน่วยความจำ (ขอบคุณ [Khoran](https://github.com/khoran)
- แสดงรายการวัตถุระยะไกลทั้งหมดในบัคเก็ต (รวมถึงวัตถุที่ไม่ได้อัปโหลดผ่าน Frappe)
- รองรับ URL ที่ลงนามล่วงหน้าของ S3 / Minio: เปิดใช้งานความสามารถในการสตรีมวิดีโอและฟังก์ชันอื่นๆ ของ S3
- URL ที่ลงนามล่วงหน้าสามารถใช้กับไฟล์ทั้งหมดในโฟลเดอร์ที่กำหนดไว้ แต่กำหนดโดย mimetype
- ไฟล์ถูกสตรีมโดยค่าเริ่มต้น
- การตั้งค่าเพิ่มเติมต่อเอกสาร External Storage:
  - แคชเฉพาะไฟล์ที่เล็กกว่า
  - แคชเป็นวินาที
  - ขนาดบัฟเฟอร์สตรีม
  - การเปิดใช้งาน URL ที่ลงนามล่วงหน้า
  - URL ที่ลงนามล่วงหน้าเฉพาะสำหรับ mimetypes ที่กำหนด
  - เวลาหมดอายุของ URL ที่ลงนามล่วงหน้า
  - ใช้ขนาดไฟล์ S3 แทนที่จะบันทึกใน Frappe File (จำเป็นสำหรับไฟล์ > 2GB)
- ... อาจลืมอะไรบางอย่าง ;)

### ตัวเลือกการไหล

- ไม่มีการกำหนดพื้นที่จัดเก็บภายนอก S3
- หรือมีการกำหนดพื้นที่จัดเก็บภายนอก S3 แต่ไม่ได้กำหนดให้กับโฟลเดอร์:
  - ไฟล์ที่อัปโหลดทั้งหมดจะถูกบันทึกในระบบไฟล์ภายใน
- มีการกำหนดพื้นที่จัดเก็บภายนอก S3 หนึ่งแห่งให้กับโฟลเดอร์ "Attachments":
  - เฉพาะไฟล์ที่อัปโหลดไปยังโฟลเดอร์นั้นจะใช้ S3 bucket นั้น
- มีการกำหนดพื้นที่จัดเก็บภายนอก S3 หนึ่งแห่งให้กับโฟลเดอร์ "Home":
  - ไฟล์ทั้งหมดที่อัปโหลดไปยัง Frappe จะถูกจัดเก็บในบัคเก็ตนั้น ยกเว้นไฟล์ที่อัปโหลดไปยัง "Attachments" ที่จะใช้บัคเก็ตที่กำหนดไว้ข้างต้น

### การดำเนินการกับไฟล์ที่มีอยู่

- หาก "ไฟล์" มี "DFP External Storage" กำหนดไว้
  - หากเปลี่ยนเป็น "DFP External Storage" อื่น ไฟล์จะถูก:
    - "ดาวน์โหลด" จากบัคเก็ตก่อนหน้า > "อัปโหลด" ไปยังบัคเก็ตใหม่ > "ลบ" จากบัคเก็ตก่อนหน้า
  - หากปล่อยว่างไว้ ไฟล์จะถูก "ดาวน์โหลด" ไปยังระบบไฟล์ภายใน > "ลบ" จากบัคเก็ต
- หาก "ไฟล์" ไม่มี "DFP External Storage" กำหนดไว้ ดังนั้นจึงอยู่ในระบบไฟล์ภายใน:
  - หากกำหนด "DFP External Storage" ไฟล์จะถูก:
    - "อัปโหลด" ไปยังบัคเก็ตนั้น > "ลบ" จากระบบไฟล์

### ตั้งค่าหรือทดลองใช้ในเครื่อง

#### ติดตั้ง Frappe 14

ปฏิบัติตามขั้นตอนทั้งหมดสำหรับระบบปฏิบัติการของคุณในคู่มือทางการ: [https://frappeframework.com/docs/v14/user/en/installation](https://frappeframework.com/docs/v14/user/en/installation)

#### สร้างสภาพแวดล้อม "frappe-bench" ส่วนตัวของคุณ (ชื่อโฟลเดอร์ปรับแต่งได้)

ในโฟลเดอร์ home ของคุณ:

```bash
cd ~
bench init frappe-bench
```

#### ติดตั้งแอป "dfp_external_storage"

```bash
cd ~/frappe-bench
bench get-app https://github.com/ManotLuijiu/dfp_external_storage.git
```

#### สร้างไซต์ใหม่พร้อมติดตั้งแอป "dfp_external_storage"

```bash
cd ~/frappe-bench
bench new-site dfp_external_storage_site.localhost --install-app dfp_external_storage
```

#### เริ่มต้นเซิร์ฟเวอร์เพื่อให้ไซต์ทำงาน

```bash
cd ~/frappe-bench
bench start
```

#### สร้าง "DFP External Storage" หนึ่งรายการหรือมากกว่า

เพิ่ม S3 bucket หนึ่งรายการหรือมากกว่า และนี่คือขั้นตอนที่สำคัญที่สุด กำหนดโฟลเดอร์ "Home" ให้กับมัน วิธีนี้ทำให้ไฟล์ทั้งหมดที่อัปโหลดไปยัง Frappe / ERPNext ถูกอัปโหลดไปยังบัคเก็ตนั้น

คุณสามารถเลือกโฟลเดอร์ที่แตกต่างกันและเฉพาะไฟล์เหล่านั้นจะถูกอัปโหลด หรือเลือกบัคเก็ตที่แตกต่างกันสำหรับโฟลเดอร์ที่แตกต่างกัน จินตนาการของคุณไม่มีขีดจำกัด!! :D

#### สตรีมข้อมูลไปและมาจาก S3 โดยไม่ต้องอ่านไฟล์ทั้งหมดเข้าหน่วยความจำ

ตัวเลือกนี้มีค่าเมื่อทำงานกับไฟล์ขนาดใหญ่

สำหรับการอัปโหลดเนื้อหาจากไฟล์ในเครื่อง การใช้งานจะดูเหมือนนี้:

```python
file_doc = frappe.get_doc({
    "doctype":"File",
    "is_private":True,
    "file_name": "ชื่อไฟล์ที่นี่"
})
file_doc.dfp_external_storage_upload_file(filepath)
file_doc.save()
```

สำหรับการดาวน์โหลดเนื้อหาไปยังไฟล์ในเครื่อง:

```python
file_doc = frappe.get_doc("File",doc_name)
file_doc.dfp-external_storage_download_to_file("/path/to/local/file")
```

สำหรับการอ่านไฟล์ระยะไกลโดยตรงผ่านวัตถุพร็อกซี:

```python
file_doc = frappe.get_doc("File",doc_name)

# อ่านสารบัญไฟล์ zip โดยไม่ต้องดาวน์โหลดไฟล์ zip ทั้งไฟล์
with zipfile.ZipFile(file_doc.dfp_external_storage_file_proxy()) as z:
  for zipinfo in z.infolist():
     print(f"{zipinfo.filename}")

```

### สิ่งที่ยังค้างอยู่

- สร้างการทดสอบ:
  - สร้าง DFP External Storage
  - อัปโหลดไฟล์ไปยังบัคเก็ต
  - อ่านไฟล์บัคเก็ต
  - ย้ายไฟล์บัคเก็ต
  - ลบไฟล์บัคเก็ต

### การมีส่วนร่วม

1. [จรรยาบรรณ](CODE_OF_CONDUCT.md)

### การยอมรับ

- cloud storage โดย Iconstock จาก [Noun Project](https://thenounproject.com/browse/icons/term/cloud-storage/)

#### ใบอนุญาต

MIT
