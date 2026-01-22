import arcpy
import os
import datetime
import logging
import re
import zipfile
import shutil
from arcgis.gis import GIS

class Toolbox(object):
    def __init__(self):
        """Define the toolbox."""
        self.label = "AGOL Backup Tools"
        self.alias = "agol_backup"
        self.tools = [BackupOrgData]

class BackupOrgData(object):
    def __init__(self):
        """Define the tool."""
        self.label = "Backup Organization Data"
        self.description = (
            "Backs up ALL Org Feature Layers and Tables. "
            "Skips Views, zips the GDB, and cleans up backups older than 30 days."
        )
        self.canRunInBackground = False

    def getParameterInfo(self):
        return []

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        return

    def updateMessages(self, parameters):
        return

    def setup_logging(self, log_dir):
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"Org_Backup_Log_{timestamp}.txt")
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='w'
        )
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger('').addHandler(console)
        return log_file

    def sanitize_name(self, name):
        """Cleans strings to be valid FGDB feature class names."""
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name)
        if clean_name and clean_name[0].isdigit():
            clean_name = "L_" + clean_name
        return clean_name

    def zip_gdb(self, gdb_path):
        """Zips the File Geodatabase folder and removes the original."""
        zip_path = gdb_path + ".zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(gdb_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    archive_name = os.path.join(os.path.basename(gdb_path), file)
                    zipf.write(full_path, archive_name)
        shutil.rmtree(gdb_path)
        return zip_path

    def cleanup_old_backups(self, backup_dir, days=30):
        """Deletes zip files older than the specified number of days."""
        now = datetime.datetime.now()
        deleted_count = 0
        for file in os.listdir(backup_dir):
            if file.endswith(".zip") and "AGOL_Backup_" in file:
                file_path = os.path.join(backup_dir, file)
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if (now - file_time).days > days:
                    os.remove(file_path)
                    deleted_count += 1
        return deleted_count

    def execute(self, parameters, messages):
        # 1. Configuration
        base_backup_dir = r"D:\AGOL_Backups"
        log_dir = os.path.join(base_backup_dir, "Logs")
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        log_file = self.setup_logging(log_dir)

        def log_msg(msg, level="info"):
            if level == "info":
                logging.info(msg)
                arcpy.AddMessage(msg)
            elif level == "warning":
                logging.warning(msg)
                arcpy.AddWarning(msg)
            elif level == "error":
                logging.error(msg)
                arcpy.AddError(msg)

        log_msg("--- Starting Organization Full Backup ---")

        try:
            # 2. Connect to AGOL
            log_msg("Connecting to ArcGIS Online...")
            gis = GIS("pro")
            log_msg(f"Connected as: {gis.users.me.username}")

            # 3. Environment Settings
            arcpy.env.overwriteOutput = True
            arcpy.env.preserveGlobalIds = True

            # 4. Search
            log_msg("Scanning Organization for Feature Services...")
            items = gis.content.search(query='type:"Feature Service"', max_items=10000)
            if not items:
                log_msg("No items found.", "warning")
                return

            # 5. Create Backup GDB
            gdb_name = f"AGOL_Backup_{date_str}.gdb"
            gdb_full_path = os.path.join(base_backup_dir, gdb_name)
            if not os.path.exists(base_backup_dir):
                os.makedirs(base_backup_dir)
            if not arcpy.Exists(gdb_full_path):
                arcpy.management.CreateFileGDB(base_backup_dir, gdb_name)

            # 6. Backup Loop
            success_count = 0
            fail_count = 0
            backed_up_urls = set()

            for i, item in enumerate(items, 1):
                if "View Service" in item.typeKeywords:
                    continue
                try:
                    # FIX: Handle NoneType [cite: 1, 15]
                    layers = (item.layers or []) + (item.tables or [])
                    if not layers:
                        continue

                    for j, layer in enumerate(layers, 1):
                        url = getattr(layer, "url", None)
                        if not url or url in backed_up_urls:
                            continue
                        
                        backed_up_urls.add(url)
                        layer_name = layer.properties.name
                        log_msg(f"Processing Item {i}: {item.title} | Layer: {layer_name}")

                        safe_item = self.sanitize_name(item.title)
                        safe_layer = self.sanitize_name(layer_name)
                        out_name = f"{safe_item}_{safe_layer}_{date_str}"[:115]
                        out_path = os.path.join(gdb_full_path, out_name)

                        if arcpy.Exists(out_path):
                            out_name = f"{out_name}_{j}"
                            out_path = os.path.join(gdb_full_path, out_name)

                        try:
                            is_spatial = hasattr(layer.properties, "geometryType") and layer.properties.geometryType
                            if is_spatial:
                                arcpy.conversion.ExportFeatures(url, out_path)
                            else:
                                arcpy.conversion.TableToTable(url, gdb_full_path, out_name)
                            success_count += 1
                        except Exception as export_err:
                            log_msg(f"     FAILED export for {layer_name}: {str(export_err)}", "error")
                            fail_count += 1
                except Exception as item_err:
                    log_msg(f"   Error accessing {item.title}: {str(item_err)}", "error")
                    fail_count += 1

            # 7. Zip and Cleanup
            if arcpy.Exists(gdb_full_path):
                log_msg("Compressing Backup GDB to ZIP...")
                final_zip = self.zip_gdb(gdb_full_path)
                log_msg(f"Backup complete: {final_zip}")
                
                log_msg("Cleaning up backups older than 30 days...")
                deleted = self.cleanup_old_backups(base_backup_dir)
                if deleted > 0:
                    log_msg(f"Removed {deleted} old backup zip(s).")

            # 8. Final Report
            log_msg("--- Backup Process Finished ---")
            log_msg(f"Layers Exported: {success_count}")
            log_msg(f"Layers Failed:   {fail_count}")

        except Exception as e:
            log_msg(f"Critical System Failure: {str(e)}", "error")
