import arcpy
import os
import datetime
import logging
import re
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
        self.description = "Backs up ALL Org Feature Layers with history, attachments, and GlobalIDs."
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
        
        # Console Handler
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

    def execute(self, parameters, messages):
        # 1. Configuration
        base_backup_dir = r"D:\AGOL_Backups"
        log_dir = os.path.join(base_backup_dir, "Logs")
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        
        # Setup Logging
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
        log_msg(f"Log location: {log_file}")

        try:
            # 2. Connect to AGOL
            log_msg("Connecting to ArcGIS Online...")
            gis = GIS("pro")
            log_msg(f"Connected as: {gis.users.me.username} (Role: {gis.users.me.role})")

            # 3. Environment Settings for Data Integrity
            arcpy.env.overwriteOutput = True
            # CRITICAL: This ensures Global IDs are kept as Global IDs
            arcpy.env.preserveGlobalIds = True 
            # Note: Attachments are handled automatically by ExportFeatures for services

            # 4. Search for ALL Feature Services in the Org
            # We remove the 'owner' filter.
            # We set max_items to 10000 to ensure we catch everything.
            log_msg("Scanning Organization for Feature Services...")
            items = gis.content.search(query="type:\"Feature Service\"", max_items=10000)
            
            if not items:
                log_msg("No items found.", "warning")
                return

            total_items = len(items)
            log_msg(f"Found {total_items} Feature Services. Sorting...")

            # 5. Complex Sorting
            # Logic: 
            #  1. Authoritative (True > False)
            #  2. Modified Date (Newest > Oldest)
            #  3. Size (Largest > Smallest) - Proxy for 'number of records'
            items.sort(
                key=lambda x: (
                    x.content_status == 'org_authoritative', 
                    x.modified, 
                    x.size
                ), 
                reverse=True
            )

            # 6. Create Backup GDB
            gdb_name = f"AGOL_Backup_{date_str}.gdb"
            gdb_full_path = os.path.join(base_backup_dir, gdb_name)
            
            if not os.path.exists(base_backup_dir):
                os.makedirs(base_backup_dir)
            
            if not arcpy.Exists(gdb_full_path):
                arcpy.management.CreateFileGDB(base_backup_dir, gdb_name)

            # 7. Backup Loop
            success_count = 0
            fail_count = 0

            for i, item in enumerate(items, 1):
                try:
                    # Detailed Messaging
                    auth_tag = "[AUTHORITATIVE]" if item.content_status == 'org_authoritative' else ""
                    log_msg(f"Processing Item {i} of {total_items}: {item.title} {auth_tag}")
                    
                    # Access layers
                    layers = item.layers + item.tables
                    total_sublayers = len(layers)

                    if total_sublayers == 0:
                        log_msg(f"   - Item {item.title} is empty. Skipping.", "warning")
                        continue

                    for j, layer in enumerate(layers, 1):
                        layer_name = layer.properties.name
                        log_msg(f"   - Backing up layer {j} of {total_sublayers}: {layer_name}")
                        
                        # Naming Convention: ItemName_LayerName_Date
                        safe_item = self.sanitize_name(item.title)
                        safe_layer = self.sanitize_name(layer_name)
                        
                        # Shorten if too long (FGDB limit ~160 chars)
                        # We leave room for the date suffix
                        prefix = f"{safe_item}_{safe_layer}"[:120]
                        out_name = f"{prefix}_{date_str}"
                        out_path = os.path.join(gdb_full_path, out_name)

                        # Check if already exists (in case of duplicate names in source)
                        if arcpy.Exists(out_path):
                            out_name = f"{out_name}_{j}" # Append index to make unique
                            out_path = os.path.join(gdb_full_path, out_name)

                        # Perform Export
                        # This pulls Attachments + GlobalIDs (due to env setting)
                        try:
                            arcpy.conversion.ExportFeatures(layer.url, out_path)
                            success_count += 1
                        except Exception as layer_error:
                            log_msg(f"     FAILED to export layer {layer_name}: {str(layer_error)}", "error")
                            fail_count += 1
                
                except Exception as item_error:
                    log_msg(f"   Error accessing item {item.title}: {str(item_error)}", "error")
                    fail_count += 1

            # 8. Final Report
            log_msg("--- Backup Process Finished ---")
            log_msg(f"Layers Exported: {success_count}")
            log_msg(f"Layers Failed:   {fail_count}")
            log_msg(f"Backup GDB:      {gdb_full_path}")

        except Exception as e:
            log_msg(f"Critical System Failure: {str(e)}", "error")
