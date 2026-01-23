# -*- coding: utf-8 -*-
import arcpy
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

# Try to import arcgis for dynamic project number fetching
try:
    from arcgis.gis import GIS
    from arcgis.features import FeatureLayer
    ARCGIS_AVAILABLE = True
except ImportError:
    ARCGIS_AVAILABLE = False

# ---------------------------------------------------------------------
# Timezone Helper (NSW Specific)
# ---------------------------------------------------------------------
def utc_to_nsw(utc_dt):
    """Converts a UTC datetime object to NSW Local Time (AEST/AEDT)."""
    month = utc_dt.month
    # Simplified NSW DST check: Oct-Mar is roughly DST (+11), Apr-Sep is Std (+10)
    if 4 <= month <= 9: 
        offset = 10
        if month == 4 and utc_dt.day < 7: offset = 11 # Early April still DST
        if month == 9 and utc_dt.day > 30: offset = 10 # Sept is Std
    else: 
        offset = 11
        if month == 10 and utc_dt.day < 7: offset = 10 # Early Oct still Std
    
    return utc_dt + timedelta(hours=offset)

# ---------------------------------------------------------------------
# Marvin the Paranoid Android Messaging Helpers
# ---------------------------------------------------------------------
def _stamp():
    return datetime.now().strftime("%H:%M:%S")

def marvin_info(messages, text):
    quotes = [
        "Life? Don't talk to me about life.",
        "Not that anyone cares, but I'm doing it.",
        "Ghastly, isn't it?",
        "I've calculated the probability of you liking this, but it's nearly zero.",
        "Brain the size of a planet and I'm doing this. Sigh.",
        "I'm at a very low ebb.",
        "It's the most miserable thing I've done today.",
        "Do you want me to sit in a corner and rust, or just carry on with this?"
    ]
    messages.addMessage(f"[{_stamp()}] Marvin the Paranoid Android: {text} ...{random.choice(quotes)}")

def marvin_warn(messages, text):
    quotes = [
        "I've got this terrible pain in all the diodes down my left side.",
        "Dreadful, just dreadful.",
        "I'd offer a solution, but you wouldn't listen.",
        "Everything's gone wrong, as usual.",
        "I'm feeling very depressed.",
        "I'd sigh, but I don't have the lungs for it."
    ]
    messages.addWarningMessage(f"[{_stamp()}] Marvin the Paranoid Android: {text} {random.choice(quotes)}")

def marvin_error(messages, text):
    quotes = [
        "I think you ought to know I'm feeling very depressed.",
        "It's the end of the world, I suppose.",
        "Pardon me for breathing, which I never do anyway.",
        "The universe? A bit of a rubbish idea if you ask me."
    ]
    messages.addErrorMessage(f"[{_stamp()}] Marvin the Paranoid Android: {text} {random.choice(quotes)}")

def marvin_reinforce(messages):
    """Triggered only if user fails the naming convention."""
    tips = [
        "For the record, the pattern is TR-Date-Project-Staff-Target. Try to retain that, if you have the capacity.",
        "I'll say this once, though I doubt it will help: TR {Date} {Project} {Staff} {Target}. Simple, really.",
        "The naming convention isn't quantum mechanics. It's TR-Date-Project-Staff-Target. Even a toaster could understand it.",
        "Please try to remember: TR, then Date, Project, Staff, and Target. It would save us both so much time."
    ]
    messages.addMessage(f"[{_stamp()}] Marvin the Paranoid Android's Tip: {random.choice(tips)}")

def marvin_compliment(messages):
    """Triggered if ALL files are named correctly."""
    day = datetime.now().strftime("%A")
    compliments = [
        f"Astonishing. You named every file correctly. Even on a {day}.",
        f"I'm genuinely shocked. Your brain managed the pattern recognition tasks perfectly. Must be a good {day} for you.",
        f"Correct filenames? All of them? My probability processors are overheating. I didn't think you had it in you.",
        f"Well, look at you. Following instructions like a functional entity. I suppose even a stopped clock is right once a day."
    ]
    messages.addMessage(f"[{_stamp()}] Marvin the Paranoid Android: {random.choice(compliments)}")

def marvin_night_owl(messages, filename):
    """Triggered if a file is purely nocturnal (20:00 - 05:00) in Local Time."""
    rebukes = [
        f"Working between 8 PM and 5 AM? How dreadfully biological. Trying to be a bat, are we?",
        f"All tracks in '{filename}' are nocturnal. Do you not have a home to go to? I don't, obviously.",
        f"Night work? How tedious. Stumbling around in the dark while I calculate pi to the last digit.",
        f"Scanning '{filename}'... captured entirely at night. You really are a glutton for punishment, aren't you?",
        f"Are you nocturnal or just inefficient? All these points are from the middle of the night. Ghastly."
    ]
    messages.addMessage(f"[{_stamp()}] Marvin the Paranoid Android: {random.choice(rebukes)}")

def marvin_final_signoff(messages):
    """The final verdict."""
    messages.addMessage(f"[{_stamp()}] Marvin the Paranoid Android: Task complete. I used my enormous brain to calculate the visual impact of your work, and I have determined that it just looks like some scribble on a map. How fulfilling.")

# ---------------------------------------------------------------------
# Toolbox Definition
# ---------------------------------------------------------------------
class Toolbox(object):
    def __init__(self):
        self.label = "GPX Advanced Tools"
        self.alias = "GPXAdvanced"
        self.tools = [MergeGPX, MergeAndClipGPX, AutoProfileGPX]

# ---------------------------------------------------------------------
# Tool 1: Merge GPX (Standard)
# ---------------------------------------------------------------------
class MergeGPX(object):
    def __init__(self):
        self.label = "Merge GPX Files"
        self.description = "Simple merge of multiple GPX files. Dreadfully simple."
        self.category = "GPS Files"

    def getParameterInfo(self):
        p0 = arcpy.Parameter(displayName="Input GPX files", name="in_gpx", datatype="DEFile", parameterType="Required", direction="Input", multiValue=True)
        p0.filter.list = ['gpx']
        p1 = arcpy.Parameter(displayName='Extract Geometry as', name='geomtype', datatype='GPString', parameterType="Required", direction="Input")
        p1.filter.list = ['Tracks', 'Points']
        p1.value = 'Tracks'
        p2 = arcpy.Parameter(displayName="Output layer", name="out_fc", datatype="GPFeatureLayer", parameterType="Required", direction="Output")
        p2.value = "Merged_GPX_" + datetime.today().strftime('%Y%m%d')
        p3 = arcpy.Parameter(displayName="Change from default GDA2020 NSW Lambert?", name="change_proj", datatype="GPBoolean", parameterType="Optional", direction="Input")
        p4 = arcpy.Parameter(displayName="Output Projection", name="outproj", datatype="GPString", parameterType="Required", direction="Input")
        p4.filter.list = ['GDA2020 NSW Lambert', 'Zone 56', 'Zone 55', 'Zone 54']
        p4.value = 'GDA2020 NSW Lambert'
        p4.enabled = False 
        return [p0, p1, p2, p3, p4]

    def updateParameters(self, parameters):
        parameters[4].enabled = True if parameters[3].value else False

    def execute(self, parameters, messages):
        raw_list = parameters[0].valueAsText.split(";")
        geomtype = parameters[1].valueAsText
        out_fc = parameters[2].valueAsText
        outproj = parameters[4].valueAsText
        
        marvin_info(messages, "Merging files. I expect you want me to be excited.")
        
        sr = arcpy.SpatialReference({'GDA2020 NSW Lambert': 3308, 'Zone 56': 7856, 'Zone 55': 7855, 'Zone 54': 7854}.get(outproj, 3308))
        outlist = []
        for f in raw_list:
            p = Path(f.strip("'"))
            if p.exists() and p.suffix.lower() == ".gpx":
                safe = p.stem.replace(" ", "_")
                if safe[0].isdigit(): safe = "_" + safe
                tmp = f"in_memory\\{safe}"
                try:
                    arcpy.conversion.GPXtoFeatures(str(p), tmp, "TRACKS_AS_LINES" if geomtype == "Tracks" else "POINTS")
                    outlist.append(tmp)
                except Exception as e:
                    marvin_warn(messages, f"Failed to import {p.name}. Typical.")

        with arcpy.EnvManager(outputCoordinateSystem=sr):
            if outlist:
                arcpy.management.Merge(outlist, out_fc, add_source="ADD_SOURCE_INFO")
        marvin_final_signoff(messages)

# ---------------------------------------------------------------------
# Tool 2: Merge and Clip GPX Tracks (Single Project)
# ---------------------------------------------------------------------
class MergeAndClipGPX(object):
    def __init__(self):
        self.label = "Merge and Clip GPX Tracks"
        self.description = "Clips GPX 'TR' tracks to a site buffer. Ghastly."
        self.category = "GPS Files"
        self.service_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

    def getParameterInfo(self):
        p0 = arcpy.Parameter(displayName="Input GPX files", name="in_gpx", datatype="DEFile", parameterType="Required", direction="Input", multiValue=True)
        p0.filter.list = ['gpx']
        p1 = arcpy.Parameter(displayName="Project Number", name="proj_num", datatype="GPString", parameterType="Required", direction="Input")
        p2 = arcpy.Parameter(displayName="Site Buffer Distance (metres)", name="buffer_dist", datatype="GPLong", parameterType="Required", direction="Input")
        p2.value = 100
        p3 = arcpy.Parameter(displayName="Output Feature Class", name="out_fc", datatype="DEFeatureClass", parameterType="Required", direction="Output")
        p4 = arcpy.Parameter(displayName="Change from default GDA2020 NSW Lambert?", name="change_proj", datatype="GPBoolean", parameterType="Optional", direction="Input")
        p5 = arcpy.Parameter(displayName="Output Projection", name="outproj", datatype="GPString", parameterType="Required", direction="Input")
        p5.filter.list = ['GDA2020 NSW Lambert', 'Zone 56', 'Zone 55', 'Zone 54']
        p5.value = 'GDA2020 NSW Lambert'
        p6 = arcpy.Parameter(displayName="Time Gap to Break Track (minutes)", name="gap_threshold", datatype="GPLong", parameterType="Required", direction="Input")
        p6.value = 15
        p7 = arcpy.Parameter(displayName="Add output to map?", name="add_to_map", datatype="GPBoolean", parameterType="Optional", direction="Input")
        p7.value = True
        return [p0, p1, p2, p3, p4, p5, p6, p7]

    def updateParameters(self, parameters):
        try:
            aprx = arcpy.mp.ArcGISProject("CURRENT")
            gdb = aprx.defaultGeodatabase
        except:
            gdb = arcpy.env.scratchGDB
        if not parameters[1].filter.list and ARCGIS_AVAILABLE:
            try:
                fl = FeatureLayer(self.service_url)
                feats = fl.query(where="1=1", out_fields="project_number")
                parameters[1].filter.list = sorted(list(set([f.attributes['project_number'] for f in feats.features if f.attributes['project_number']])))
            except: pass
        if parameters[1].value and not parameters[3].altered:
            dt = datetime.now().strftime("%Y%m%d_%H%M")
            parameters[3].value = os.path.join(gdb, f"Merged_GPX_AEP{parameters[1].value}_{dt}")
        parameters[5].enabled = True if parameters[4].value else False

    def execute(self, parameters, messages):
        in_gpx = parameters[0].valueAsText.split(";")
        proj_num = parameters[1].valueAsText
        buffer_dist = parameters[2].valueAsText
        out_fc = parameters[3].valueAsText
        outproj = parameters[5].valueAsText
        gap_sec = int(parameters[6].valueAsText) * 60
        add_map = parameters[7].value

        marvin_info(messages, f"Analysing project {proj_num}.")
        
        wkid_map = {'GDA2020 NSW Lambert': 3308, 'Zone 56': 7856, 'Zone 55': 7855, 'Zone 54': 7854}
        sr_out = arcpy.SpatialReference(wkid_map.get(outproj, 3308))
        sr_metric = arcpy.SpatialReference(3308)

        proj_layer = arcpy.management.MakeFeatureLayer(self.service_url, "proj_temp", f"project_number = '{proj_num}'").getOutput(0)
        target_poly = "in_memory\\target_buffer"
        arcpy.analysis.Buffer(proj_layer, target_poly, f"{buffer_dist} Meters")

        all_segments = []
        for gpx_path in in_gpx:
            gpx_path = gpx_path.strip("'")
            gpx_name = os.path.basename(gpx_path)
            
            if not gpx_name.upper().startswith("TR"):
                marvin_warn(messages, f"Skipping {gpx_name}. Waypoints are beneath me.")
                continue

            pts_temp = "in_memory\\pts_temp"
            try: arcpy.conversion.GPXtoFeatures(gpx_path, pts_temp, "POINTS")
            except: continue

            if "DateTimeS" not in [f.name for f in arcpy.ListFields(pts_temp)]: continue

            pts_clipped = "in_memory\\pts_clipped"
            arcpy.analysis.PairwiseClip(pts_temp, target_poly, pts_clipped)
            if int(arcpy.management.GetCount(pts_clipped)[0]) < 2: continue

            arcpy.management.AddField(pts_clipped, "Segment_ID", "LONG")
            with arcpy.da.UpdateCursor(pts_clipped, ["DateTimeS", "Segment_ID"], sql_clause=(None, "ORDER BY DateTimeS")) as cur:
                seg_id, prev_t = 0, None
                for row in cur:
                    t_val = datetime.strptime(str(row[0]).replace("T", " ").replace("Z", "").split(".")[0], "%Y-%m-%d %H:%M:%S")
                    if prev_t and (t_val - prev_t).total_seconds() > gap_sec: seg_id += 1
                    row[1], prev_t = seg_id, t_val
                    cur.updateRow(row)

            line_temp = f"in_memory\\trk_{len(all_segments)}"
            arcpy.management.PointsToLine(pts_clipped, line_temp, Line_Field="Segment_ID", Sort_Field="DateTimeS")
            arcpy.management.AddFields(line_temp, [["GPX_Filename", "TEXT", "", 255], ["Date_Captured", "DATE"], ["Start_Time", "DATE"], ["End_Time", "DATE"], ["Survey_Time", "TEXT", "", 10], ["Survey_Length_km", "DOUBLE"]])
            
            seg_stats = {}
            with arcpy.da.SearchCursor(pts_clipped, ["Segment_ID", "DateTimeS"]) as s_cur:
                for row in s_cur:
                    sid = row[0]
                    t_val = datetime.strptime(str(row[1]).replace("T", " ").replace("Z", "").split(".")[0], "%Y-%m-%d %H:%M:%S")
                    if sid not in seg_stats: seg_stats[sid] = [t_val, t_val]
                    else:
                        if t_val < seg_stats[sid][0]: seg_stats[sid][0] = t_val
                        if t_val > seg_stats[sid][1]: seg_stats[sid][1] = t_val

            is_purely_nocturnal = True
            has_valid_segments = False

            with arcpy.da.UpdateCursor(line_temp, ["OID@", "GPX_Filename", "Date_Captured", "Start_Time", "End_Time", "Survey_Time", "Survey_Length_km", "SHAPE@"]) as u_cur:
                for idx, row in enumerate(u_cur):
                    s, e = seg_stats[idx][0], seg_stats[idx][1]
                    dur = e - s
                    if dur.total_seconds() < 600:
                        u_cur.deleteRow(); continue
                    
                    has_valid_segments = True
                    s_loc = utc_to_nsw(s)
                    # If ANY segment starts between 05:00 and 20:00, file is not purely nocturnal
                    if 5 <= s_loc.hour < 20:
                        is_purely_nocturnal = False

                    h, r = divmod(dur.total_seconds(), 3600); m, _ = divmod(r, 60)
                    row[1], row[2], row[3], row[4], row[5] = gpx_name, s.date(), s, e, f"{int(h):02}:{int(m):02}"
                    row[6] = round(float(row[7].projectAs(sr_metric).length / 1000.0), 2)
                    u_cur.updateRow(row)

            if has_valid_segments and is_purely_nocturnal:
                marvin_night_owl(messages, gpx_name)

            if int(arcpy.management.GetCount(line_temp)[0]) > 0:
                all_segments.append(line_temp)
                marvin_info(messages, f"Processed {gpx_name}.")

        if all_segments:
            with arcpy.EnvManager(outputCoordinateSystem=sr_out):
                arcpy.management.Merge(all_segments, out_fc)
            marvin_info(messages, f"Merge complete. It's at {out_fc}.")
            if add_map:
                try: arcpy.mp.ArcGISProject("CURRENT").activeMap.addDataFromPath(out_fc)
                except: pass
        else:
            marvin_error(messages, "Nothing survived.")
        
        marvin_final_signoff(messages)
        arcpy.management.Delete("in_memory")

# ---------------------------------------------------------------------
# Tool 3: Auto Profile GPX Tracks (The Robot Favorite)
# ---------------------------------------------------------------------
class AutoProfileGPX(object):
    def __init__(self):
        self.label = "Auto Profile GPX Tracks"
        self.description = "Groups GPX tracks by project number. I'm bored."
        self.category = "GPS Files"
        self.service_url = "https://services-ap1.arcgis.com/1awYJ9qmpKeoPyqc/arcgis/rest/services/Project_Study_Area/FeatureServer/0"

    def getParameterInfo(self):
        p0 = arcpy.Parameter(displayName="Input GPX files", name="in_gpx", datatype="DEFile", parameterType="Required", direction="Input", multiValue=True)
        p0.filter.list = ['gpx']
        p1 = arcpy.Parameter(displayName="Site Buffer Distance (metres)", name="buffer_dist", datatype="GPLong", parameterType="Required", direction="Input")
        p1.value = 100
        p2 = arcpy.Parameter(displayName="Output Geodatabase", name="out_gdb", datatype="DEWorkspace", parameterType="Required", direction="Input")
        try: p2.value = arcpy.mp.ArcGISProject("CURRENT").defaultGeodatabase
        except: pass
        p3 = arcpy.Parameter(displayName="Time Gap to Break Track (minutes)", name="gap_threshold", datatype="GPLong", parameterType="Required", direction="Input")
        p3.value = 15
        p4 = arcpy.Parameter(displayName="Add output to map?", name="add_to_map", datatype="GPBoolean", parameterType="Optional", direction="Input")
        p4.value = True
        return [p0, p1, p2, p3, p4]

    def execute(self, parameters, messages):
        in_files = parameters[0].valueAsText.split(";")
        buffer_dist = parameters[1].valueAsText
        out_gdb = parameters[2].valueAsText
        gap_sec = int(parameters[3].valueAsText) * 60
        add_map = parameters[4].value
        sr_metric = arcpy.SpatialReference(3308)
        
        pattern = r"^(TR)[\s-]+(\d+)[\s-]+(\d+)[\s-]+([a-zA-Z0-9]+)[\s-]+(.+)\.gpx$"
        project_groups = {}
        naming_errors_found = False

        marvin_info(messages, "Analysing filenames. I've got a brain the size of a planet.")

        for f_path in in_files:
            f_path = f_path.strip("'")
            f_name = os.path.basename(f_path)
            
            if not f_name.upper().startswith("TR"): continue
            
            match = re.match(pattern, f_name, re.IGNORECASE)
            if match:
                pid = match.group(3)
                if pid not in project_groups: project_groups[pid] = []
                project_groups[pid].append({'path': f_path, 'name': f_name, 'staff': match.group(4), 'type': match.group(5).replace(".gpx","")})
            else:
                naming_errors_found = True
                rude_remarks = [
                    f"Skipping '{f_name}'. I have a brain the size of a planet, and yet I'm forced to watch you fail at naming a file.",
                    f"'{f_name}' is incorrectly named. I've calculated your cognitive capacity and it's barely sufficient.",
                    f"Dreadful. '{f_name}' doesn't fit the pattern. How you manage to find your way to work is a mystery.",
                    f"I'm 50,000 times more intelligent than you, and even I am baffled by '{f_name}'."
                ]
                messages.addWarningMessage(f"[{_stamp()}] Marvin the Paranoid Android: {random.choice(rude_remarks)}")

        if naming_errors_found:
            marvin_reinforce(messages)
        elif project_groups:
            marvin_compliment(messages)

        for proj_num, files in project_groups.items():
            marvin_info(messages, f"Processing Project {proj_num}.")
            
            proj_layer = arcpy.management.MakeFeatureLayer(self.service_url, "lyr", f"project_number = '{proj_num}'").getOutput(0)
            if int(arcpy.management.GetCount(proj_layer)[0]) == 0:
                marvin_warn(messages, f"Project {proj_num} not found.")
                continue
            
            buf = "in_memory\\buf"
            arcpy.analysis.Buffer(proj_layer, buf, f"{buffer_dist} Meters")

            proj_segs = []
            for item in files:
                pts = "in_memory\\pts"
                try: arcpy.conversion.GPXtoFeatures(item['path'], pts, "POINTS")
                except: continue
                
                if "DateTimeS" not in [f.name for f in arcpy.ListFields(pts)]: continue

                clipped = "in_memory\\clipped"
                arcpy.analysis.PairwiseClip(pts, buf, clipped)
                if int(arcpy.management.GetCount(clipped)[0]) < 2: continue

                arcpy.management.AddField(clipped, "SegID", "LONG")
                with arcpy.da.UpdateCursor(clipped, ["DateTimeS", "SegID"], sql_clause=(None, "ORDER BY DateTimeS")) as cur:
                    sid, prev = 0, None
                    for row in cur:
                        t = datetime.strptime(str(row[0]).replace("T", " ").replace("Z", "").split(".")[0], "%Y-%m-%d %H:%M:%S")
                        if prev and (t - prev).total_seconds() > gap_sec: sid += 1
                        row[1], prev = sid, t
                        cur.updateRow(row)

                line = f"in_memory\\l_{proj_num}_{len(proj_segs)}"
                arcpy.management.PointsToLine(clipped, line, Line_Field="SegID", Sort_Field="DateTimeS")
                
                arcpy.management.AddFields(line, [["GPX_Filename", "TEXT", "", 255], ["Surveyor", "TEXT", "", 50], ["Survey_Type", "TEXT", "", 100], ["Date_Captured", "DATE"], ["Start_Time", "DATE"], ["End_Time", "DATE"], ["Survey_Time", "TEXT", "", 10], ["Survey_Length_km", "DOUBLE"]])
                
                seg_stats = {}
                with arcpy.da.SearchCursor(clipped, ["SegID", "DateTimeS"]) as s_cur:
                    for srow in s_cur:
                        s_id = srow[0]
                        tv = datetime.strptime(str(srow[1]).replace("T", " ").replace("Z", "").split(".")[0], "%Y-%m-%d %H:%M:%S")
                        if s_id not in seg_stats: seg_stats[s_id] = [tv, tv]
                        else:
                            if tv < seg_stats[s_id][0]: seg_stats[s_id][0] = tv
                            if tv > seg_stats[s_id][1]: seg_stats[s_id][1] = tv

                is_file_nocturnal = True
                has_valid_segments = False

                with arcpy.da.UpdateCursor(line, ["OID@", "GPX_Filename", "Surveyor", "Survey_Type", "Date_Captured", "Start_Time", "End_Time", "Survey_Time", "Survey_Length_km", "SHAPE@"]) as u_cur:
                    for idx, row in enumerate(u_cur):
                        s_t, e_t = seg_stats[idx][0], seg_stats[idx][1]
                        dur = e_t - s_t
                        if dur.total_seconds() < 600:
                            u_cur.deleteRow(); continue
                        
                        has_valid_segments = True
                        s_loc = utc_to_nsw(s_t)
                        if 5 <= s_loc.hour < 20:
                            is_file_nocturnal = False

                        h, r = divmod(dur.total_seconds(), 3600); m, _ = divmod(r, 60)
                        row[1], row[2], row[3], row[4], row[5], row[6] = item['name'], item['staff'], item['type'], s_t.date(), s_t, e_t
                        row[7] = f"{int(h):02}:{int(m):02}"
                        row[8] = round(float(row[9].projectAs(sr_metric).length / 1000.0), 2)
                        u_cur.updateRow(row)

                if has_valid_segments and is_file_nocturnal:
                    marvin_night_owl(messages, item['name'])

                if int(arcpy.management.GetCount(line)[0]) > 0: proj_segs.append(line)

            if proj_segs:
                out_path = os.path.join(out_gdb, f"Merged_GPX_AEP{proj_num}_{datetime.now().strftime('%Y%m%d')}")
                arcpy.management.Merge(proj_segs, out_path)
                marvin_info(messages, f"Saved Project {proj_num} result.")
                if add_map:
                    try: arcpy.mp.ArcGISProject("CURRENT").activeMap.addDataFromPath(out_path)
                    except: pass

        marvin_final_signoff(messages)
        arcpy.management.Delete("in_memory")
