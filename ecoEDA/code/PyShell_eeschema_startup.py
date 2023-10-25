import os # DO NOT MOVE THESE LINES
ecoEDA_dir = "/Users/jasminelu/Documents/00_Research Projects/ecoEDA/public_git/ecoEDA/ecoEDA/code/"

fp_dir = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"

import sys 

sys.path.append(ecoEDA_dir)

from ecoEDA_lib_utils import get_sym_elements_for_component
from fp_utils import get_fp_draw_elements, get_fp_path, get_fp_path_missing_lib, get_order
from schematic_rw import get_subcircuit_draw_elements

import time
import json
import re

from pythonosc import dispatcher
from pythonosc import osc_server
from pythonosc import udp_client

import threading
import logging

import wx


lib_path = ecoEDA_dir + "ecoEDA.kicad_sym"


#get working directory
def getdirpath(file):
    return ecoEDA_dir + file

#class for storing information about suggestions and helper functions
class Suggestion_Helper():
    def __init__(self):
        '''
        suggestions_dict - dict full of passed information about suggestions
        unfiltered_suggestions_dict - copy of unfiltered list of suggestions so filters can be applied
        orig_part_dict - dict full of information about the part to be replaced
        sugg_components - array of the suggested components by name
        matched_part_dict - if the match type is a single match, then a dict with the specific matched part info
        locked suggestions - don't pull up suggestions while reviewing is happening
        '''

        self.suggestions_dict = {}
        self.unfiltered_suggestions_dict = {}

        self.orig_part_dict = {}
        self.sugg_components = []

        self.matched_part_dict = {}

        self.lock_suggestions = False

        self.filters = {"dk_sim": True,"val_dist": False,"smd": False,"tht": False}

    def reset_vals(self):
        '''
            Reset helper values so that previous values don't remain
        '''
        self.sugg_components = []

    def filter_suggestions(self):
        '''
            Use filtering UI to update suggestions in UI
        '''
        #reset
        self.suggestions_dict = self.unfiltered_suggestions_dict.copy()

        #remove first
        if self.filters["smd"] and not self.filters["tht"]:
            self.suggestions_dict = self.footprint_filter(self.suggestions_dict, "THT")
        elif self.filters["tht"] and not self.filters["smd"]:
            self.suggestions_dict = self.footprint_filter(self.suggestions_dict, "SMD")

        self.sugg_components = list(self.suggestions_dict.keys())

        #sort after
        if self.filters["val_dist"]:
            sorted_val_cmpnts = self.value_dist_filter(self.suggestions_dict)
            self.sugg_components = sorted_val_cmpnts


    def footprint_filter(self, suggestions_dict, rm_fp_type):
        '''
            Filtering function depending on whether SMD or THT types should be removed
        '''
        for cmpn in list(suggestions_dict):
            if suggestions_dict[cmpn]['SMD vs. THT'] == rm_fp_type:
                suggestions_dict.pop(cmpn)
        return suggestions_dict

    def split_on_letter(self, s):
        '''
            Helper function for getting values for passive components - identifying numeric and letter values
        '''

        i = 0
        for i,c in enumerate(s):
            if not c.isdigit() and c!= '.':
                break

        if i >= 1:
            if s[i].isdigit():
                number=s[:i+1]
            else:
                number=s[:i]
        elif i == 0 and len(s) > 0:
            number = s[0]
        else:
            number = ''
        unit=s[i:]

        return number, unit

    def get_mod_value(self, value_txt, cmpnt_value):
        '''
            Getting distance between component value and suggested values
        '''
        val_num, val_char = self.split_on_letter(value_txt)
        if len(val_num) < 1:
            return float("inf")
        elif len(val_char) < 1:
            return abs(float(val_num) - cmpnt_value)
        elif val_char[0]=='M':
            return abs((float(val_num) * 1000000) - cmpnt_value)
        elif val_char[0]=='m':
            return abs((float(val_num) * 0.001) - cmpnt_value)
        elif val_char[0]=='u':
            return abs((float(val_num) * 0.000001) - cmpnt_value)
        elif val_char[0]=='n':
            return abs((float(val_num) * 0.000000001) - cmpnt_value)
        elif val_char[0]=='p':
            return abs((float(val_num) * 0.000000000001) - cmpnt_value)
        return float(val_num)

    def get_num_value(self,value_txt):
        '''
            Multiplying values by the abbreviated multiple
        '''
        
        val_num, val_char = self.split_on_letter(value_txt)

        if len(val_num) < 1:
            return float("inf")
        elif len(val_char) < 1:
            return float(val_num)
        elif val_char[0]=='M':
            return float(val_num) * 1000000
        elif val_char[0]=='k':
            return float(val_num) * 1000
        elif val_char[0]=='K':
            return float(val_num) * 1000
        elif val_char[0]=='m':
            return float(val_num) * 0.001
        elif val_char[0]=='u':
            return float(val_num) * 0.000001
        elif val_char[0]=='n':
            return float(val_num) * 0.000000001
        elif val_char[0]=='p':
            return float(val_num) * 0.000000000001
        elif val_char[0]== 'O':
            return float(val_num) * 1.00
        elif val_char[0]== 'o':
            return float(val_num) * 1.00
        elif val_char[0]== 'F':
            return float(val_num) * 1.00
        elif val_char[0]== 'f':
            return float(val_num) * 1.00
        return float(val_num)

    def value_dist_filter(self, suggestions_dict):
        '''
            Filters list by value distance
        '''
        cmpnt_value = self.get_num_value(self.orig_part_dict['value'])
        sorted_vdist_dict = sorted(suggestions_dict, key=lambda e: self.get_mod_value(suggestions_dict[e]['Value'], cmpnt_value))
        return sorted_vdist_dict

class Exact_Match_Notif(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for match notification
        '''

        #NOTIF FRAME STRUCTURE
        super(Exact_Match_Notif, self).__init__(parent, pos=(1000,200), size = (320,100), style=wx.FRAME_NO_TASKBAR|wx.STAY_ON_TOP)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        lbl.SetLabel("new ecoEDA suggestion!")

        #EXACT MATCH TEXT + COMPONENT NAME
        self.lbl_type = wx.StaticText(panel, -1, style=wx.ALIGN_LEFT)
        self.lbl_type.SetLabel("exact match - COMPONENT_NAME")
        font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.lbl_type.SetFont(font_lbl_type)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(290,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        hbox2.AddSpacer(40)
        hbox2.Add(self.lbl_type, 0, wx.ALIGN_LEFT)

        # ACCEPT / REVIEW BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(40)
        btn_accept = wx.Button(panel, -1, "accept")
        btn_accept.SetDefault()
        btn_accept.Bind(wx.EVT_BUTTON, self.OnReplace)
        
        hbox3.Add(btn_accept, 0, wx.ALIGN_LEFT)
        btn_review = wx.Button(panel,-1,"review")
        
        hbox3.AddSpacer(10)
        hbox3.Add(btn_review, 0, wx.ALIGN_LEFT)
        btn_review.Bind(wx.EVT_BUTTON, self.OnReview)
        hbox3.AddSpacer(40)

        vbox.AddSpacer(5)
        vbox.Add(hbox,1,wx.ALIGN_LEFT)
        vbox.Add(hbox2, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)
        vbox.Add(hbox3, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)

        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReview(self, event):
        self.Hide()
        exact_match_review.Update()
        exact_match_review.Show()

    def set_component(self, component):
        '''
        modify notification text if the name is too long and resize text
        '''
        if len(component) < 14:
            font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 17:
            font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 21:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:21] + "..."
        self.lbl_type.SetFont(font_lbl_type)
        self.lbl_type.SetLabel("exact match - " + component)
        client.send_message("/kicad_log", "exact match for " + component)

    def OnReplace(self, event):
        self.Hide()
        #SEND MESSAGE TO LOCAL SERVER 
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # TO DO: CHECK IF THIS NEEDS TO CHANGE DEPENDING ON SYSTEM, COULD DO FOR LOOP AND CHECK MENU ITEM VIA GETITEMLABELTEXT()
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

class Exact_Match_Review(wx.Frame):
    def __init__(self, parent, title):
        #EXACT MATCH REVIEW FRAME STRUCTURE
        super(Exact_Match_Review, self).__init__(parent, pos=(500,200), size = (500,370), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(470,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        #HEADING
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)

        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER_HORIZONTAL)
        font_lbl = wx.Font(24, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("review exact match")
        lbl.Wrap(700)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.AddSpacer(10)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)

        vbox.AddSpacer(10)
        vbox.Add(hbox,1,wx.EXPAND)
        vbox.AddSpacer(10)

        # COMPONENT COMPARISON SECTION

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox = wx.GridSizer(0,2,0,20) # for component comparison

        #top labels for pictures
        orig_lbl = wx.StaticText(panel,-1)
        font_top_lbl = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        orig_lbl.SetFont(font_top_lbl)
        orig_lbl.SetLabel("ORIGINAL")
        sugg_lbl = wx.StaticText(panel,-1)
        sugg_lbl.SetFont(font_top_lbl)
        sugg_lbl.SetLabel("SUGGESTED")

        #component names
        self.old_cmpn_lbl = wx.StaticText(panel,-1, "original component name", style = wx.ALIGN_CENTER_HORIZONTAL)
        old_cmpn_font = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.old_cmpn_lbl.SetFont(old_cmpn_font)

        #suggestion
        self.sugg_cmpn_lbl =wx.StaticText(panel,-1, "suggested component name", style = wx.ALIGN_CENTER_HORIZONTAL)
        self.sugg_cmpn_lbl.SetFont(old_cmpn_font)

        
        #Preview Images
        draw_elements_old = []
        draw_elements_new = [] #these get filled on Update

        self.old_sym_preview = SymbolPreviewPanel(panel, draw_elements_old)
        self.new_sym_preview = SymbolPreviewPanel(panel, draw_elements_new)

        #component details
        self.desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.desc.SetFont(desc_font)
        self.desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.desc.Wrap(200)

        self.keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        keywords_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.keywords.SetFont(keywords_font)
        self.keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_desc.SetFont(desc_font)
        self.n_desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.n_desc.Wrap(200)

        self.n_keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_keywords.SetFont(keywords_font)
        self.n_keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_source = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_source.SetFont(keywords_font)
        self.n_source.SetLabel("SOURCE: Lorem ipsum dolor sit amet")

        self.n_quantity = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_quantity.SetFont(keywords_font)
        self.n_quantity.SetLabel("QUANTITY: 1")


        #LAYOUT FOR ALL ELEMENTS
        #vboxes for each column
        vbox_orig = wx.BoxSizer(wx.VERTICAL)
        vbox_repl = wx.BoxSizer(wx.VERTICAL)

        #add to each column
        vbox_orig.Add(orig_lbl)
        vbox_orig.AddSpacer(5)
        vbox_orig.Add(self.old_cmpn_lbl)
        vbox_orig.AddSpacer(10)

        vbox_repl.Add(sugg_lbl)
        vbox_repl.AddSpacer(5)
        vbox_repl.Add(self.sugg_cmpn_lbl)
        vbox_repl.AddSpacer(10)

        #add to grid
        gridbox.Add(vbox_orig, 0, wx.ALL, border=0)
        gridbox.Add(vbox_repl,0, wx.ALL, border=0)

        hbox1.AddSpacer(20)
        hbox1.Add(gridbox, 1, wx.EXPAND)
        hbox1.AddSpacer(20)


        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox1 = wx.GridSizer(0,2,0,20) # for component comparison layer 2

        #vboxes for each column layer 2
        vbox_orig1 = wx.BoxSizer(wx.VERTICAL)
        vbox_repl1 = wx.BoxSizer(wx.VERTICAL)

        vbox_orig1.Add(self.old_sym_preview)
        vbox_orig1.AddSpacer(15)
        vbox_orig1.Add(self.desc)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.keywords)

        vbox_repl1.Add(self.new_sym_preview)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_desc)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_keywords)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_source)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_quantity)

        gridbox1.Add(vbox_orig1, 0, wx.ALL)
        gridbox1.Add(vbox_repl1, 0, wx.ALL)

        hbox2.AddSpacer(20)
        hbox2.Add(gridbox1, 1, wx.EXPAND)
        hbox2.AddSpacer(20)

        vbox.Add(hbox1, 1, wx.EXPAND)
        vbox.Add(hbox2,1,wx.EXPAND)

        vbox.AddSpacer(15)

        # REPLACE / CANCEL BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(20)
        btn_more_options = wx.Button(panel, -1, "see more options")
        btn_more_options.Bind(wx.EVT_BUTTON, self.OnSeeMore)
        hbox3.Add(btn_more_options, 0, wx.CENTER)
        hbox3.AddSpacer(50)
        btn_replace = wx.Button(panel,-1, "replace")
        btn_replace.SetDefault()
        hbox3.Add(btn_replace, 0, wx.ALIGN_CENTER)
        btn_replace.Bind(wx.EVT_BUTTON, self.OnReplace)
        hbox3.AddSpacer(12)
        btn_dismiss = wx.Button(panel,-1, "cancel")
        hbox3.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)
        hbox3.AddSpacer(20)
        vbox.Add(hbox3,1, wx.ALIGN_RIGHT)
        vbox.AddSpacer(15)

        panel.SetSizer(vbox)

    def Update(self):
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        o_partname = helper.orig_part_dict["lib_id"]
        o_reference = helper.orig_part_dict["reference"]

        self.old_cmpn_lbl.SetLabel(o_partname)
        self.sugg_cmpn_lbl.SetLabel(helper.matched_part_dict["lib_id"])

        o_partname_str = o_partname.split(":")[1]
        n_partname_str = helper.matched_part_dict["lib_id"].split(":")[1]

        # DRAW LIST FOR SUGGESTED SYMBOL FROM LIB UTILS FUNCTION
        self.new_sym_preview.draw_list, bounds = get_sym_elements_for_component(lib_path, n_partname_str)
        width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
        height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

        if width > 0 and height > 0:
            scale = min(200/(width+10), 115/(height+10))

            self.new_sym_preview.scale = scale
            self.new_sym_preview.min_x = bounds['min_x']
            self.new_sym_preview.max_y = bounds['max_y']
            self.new_sym_preview.width = width
            self.new_sym_preview.height = height

        self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)

        # DRAW LIST FOR ORIGINAL SYMBOL FROM DISPATCH
        
        if 'Symbol Elements' in helper.orig_part_dict.keys():
            self.old_sym_preview.draw_list = helper.orig_part_dict['Symbol Elements']
            if 'Symbol Bounds' in helper.orig_part_dict.keys():
                bounds = helper.orig_part_dict['Symbol Bounds']
                width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
                height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

                if width > 0 and height > 0:
                    scale = min(200/(width+10), 115/(height+10))

                    self.old_sym_preview.scale = scale
                    self.old_sym_preview.min_x = bounds['min_x']
                    self.old_sym_preview.max_y = bounds['max_y']
                    self.old_sym_preview.width = width
                    self.old_sym_preview.height = height
            self.Bind(wx.EVT_PAINT, self.old_sym_preview.OnPaint)
        
        # DESCRIPTION, KEYWORDS, ETC. TEXT
        # check length to avoid overflow

        desc_text = helper.orig_part_dict["ki_description"]
        if len(desc_text) > 110:
            desc_text = desc_text[:110] + "..."
        kw_text = helper.orig_part_dict["ki_keywords"]
        if len(kw_text) > 28:
            kw_text = kw_text[:28] + "..."

        self.desc.SetLabel(desc_text)
        self.desc.Wrap(200)
        self.keywords.SetLabel("KEYWORDS: " + kw_text)
        self.keywords.Wrap(200)

        s_desc_text = helper.matched_part_dict["ki_description"]
        if len(s_desc_text) > 110:
            s_desc_text = s_desc_text[:110] + "..."

        s_kw_text = helper.matched_part_dict["ki_keywords"]
        if len(s_kw_text) > 28:
            s_kw_text = s_kw_text[:28] + "..."

        s_source_text = helper.matched_part_dict["Source"]
        if len(s_source_text) > 30:
            s_source_text = s_source_text[:30] + "..."

        self.n_desc.SetLabel(s_desc_text)
        self.n_desc.Wrap(200)
        self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)

        self.n_source.SetLabel("SOURCE: " + s_source_text)
        self.n_quantity.SetLabel("QUANTITY: " + helper.matched_part_dict["Quantity"])

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReplace(self, event):
        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnSeeMore(self, event):
        self.Hide()
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/see_ranked", json.dumps(helper.orig_part_dict))
        helper.lock_suggestions = False

class Drop_In_Notif(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for suggestion notification
        '''

        #NOTIF FRAME STRUCTURE
        super(Drop_In_Notif, self).__init__(parent, pos=(1000,200), size = (320,100), style=wx.FRAME_NO_TASKBAR|wx.STAY_ON_TOP)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)

        lbl.SetLabel("new ecoEDA suggestion!")

        # DROP IN TEXT + COMPONENT NAME
        self.lbl_type = wx.StaticText(panel, -1, style=wx.ALIGN_LEFT)
        self.lbl_type.SetLabel("drop-in - ")
        font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.lbl_type.SetFont(font_lbl_type)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(290,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        hbox2.AddSpacer(40)
        hbox2.Add(self.lbl_type, 0, wx.ALIGN_LEFT)

        # ACCEPT / REVIEW BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(40)
        btn_accept = wx.Button(panel, -1, "accept")
        btn_accept.SetDefault()
        btn_accept.Bind(wx.EVT_BUTTON, self.OnReplace)

        hbox3.Add(btn_accept, 0, wx.ALIGN_LEFT)
        btn_review = wx.Button(panel,-1,"review")
        
        hbox3.AddSpacer(10)
        hbox3.Add(btn_review, 0, wx.ALIGN_LEFT)
        btn_review.Bind(wx.EVT_BUTTON, self.OnReview)
        hbox3.AddSpacer(40)

        vbox.AddSpacer(5)
        vbox.Add(hbox,1,wx.ALIGN_LEFT)
        vbox.Add(hbox2, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)
        vbox.Add(hbox3, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)

        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReview(self, event):
        self.Hide()
        drop_in_review.Update()
        drop_in_review.Show()

    def set_component(self, component):
        '''
        modify notification text if the name is too long and resize text
        '''
        if len(component) < 20:
            font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 23:
            font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 27:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:27] + "..."
        self.lbl_type.SetFont(font_lbl_type)
        self.lbl_type.SetLabel("drop-in - " + component)
        client.send_message("/kicad_log", "drop in for " + component)

    def OnReplace(self, event):
        self.Hide()
        #SEND MESSAGE TO LOCAL SERVER 
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # TO DO: CHECK IF THIS NEEDS TO CHANGE DEPENDING ON SYSTEM, COULD DO FOR LOOP AND CHECK MENU ITEM VIA GETITEMLABELTEXT()
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

class Drop_In_Review(wx.Frame):
    def __init__(self, parent, title):
        #DROP IN REVIEW FRAME STRUCTURE
        super(Drop_In_Review, self).__init__(parent, pos=(500,200), size = (500,420), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(470,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        #HEADING
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)

        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER_HORIZONTAL)
        font_lbl = wx.Font(24, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("review drop in replacement")
        lbl.Wrap(700)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.AddSpacer(10)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)

        vbox.AddSpacer(10)
        vbox.Add(hbox,1,wx.EXPAND)
        vbox.AddSpacer(10)

        # COMPONENT COMPARISON SECTION

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox = wx.GridSizer(0,2,0,20) # for component comparison

        #top labels for pictures
        orig_lbl = wx.StaticText(panel,-1)
        font_top_lbl = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        orig_lbl.SetFont(font_top_lbl)
        orig_lbl.SetLabel("ORIGINAL")
        sugg_lbl = wx.StaticText(panel,-1)
        sugg_lbl.SetFont(font_top_lbl)
        sugg_lbl.SetLabel("SUGGESTED")

        #component names
        self.old_cmpn_lbl = wx.StaticText(panel,-1, "ORIGINAL COMPONENT NAME", style = wx.ALIGN_CENTER_HORIZONTAL)
        old_cmpn_font = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.old_cmpn_lbl.SetFont(old_cmpn_font)

        #suggestion
        self.sugg_cmpn_lbl =wx.StaticText(panel,-1, "SUGGESTED COMPONENT NAME", style = wx.ALIGN_CENTER_HORIZONTAL)
        self.sugg_cmpn_lbl.SetFont(old_cmpn_font)

        #Preview Images
        draw_elements_old = []
        draw_elements_new = [] #these get filled on Update

        self.old_sym_preview = SymbolPreviewPanel(panel, draw_elements_old)
        self.new_sym_preview = SymbolPreviewPanel(panel, draw_elements_new)


        #component details
        self.desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.desc.SetFont(desc_font)
        self.desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.desc.Wrap(200)

        self.keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        keywords_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.keywords.SetFont(keywords_font)
        self.keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.footprint = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.footprint.SetFont(keywords_font)
        self.footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_desc.SetFont(desc_font)
        self.n_desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.n_desc.Wrap(200)

        self.n_keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_keywords.SetFont(keywords_font)
        self.n_keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_footprint = wx.StaticText(panel,-1,style=wx.ALIGN_LEFT)
        self.n_footprint.SetFont(keywords_font)
        self.n_footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_source = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_source.SetFont(keywords_font)
        self.n_source.SetLabel("SOURCE: Lorem ipsum dolor sit amet")

        self.n_quantity = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_quantity.SetFont(keywords_font)
        self.n_quantity.SetLabel("QUANTITY: 1")

        #LAYOUT FOR ALL ELEMENTS
        #vboxes for each column
        vbox_orig = wx.BoxSizer(wx.VERTICAL)
        vbox_repl = wx.BoxSizer(wx.VERTICAL)

        #add to each column
        vbox_orig.Add(orig_lbl)
        vbox_orig.AddSpacer(5)
        vbox_orig.Add(self.old_cmpn_lbl)
        vbox_orig.AddSpacer(10)

        vbox_repl.Add(sugg_lbl)
        vbox_repl.AddSpacer(5)
        vbox_repl.Add(self.sugg_cmpn_lbl)
        vbox_repl.AddSpacer(10)

        #add to grid
        gridbox.Add(vbox_orig, 0, wx.ALL, border=0)
        gridbox.Add(vbox_repl,0, wx.ALL, border=0)

        hbox1.AddSpacer(20)
        hbox1.Add(gridbox, 1, wx.EXPAND)
        hbox1.AddSpacer(20)


        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox1 = wx.GridSizer(0,2,0,20) # for component comparison layer 2

        #vboxes for each column layer 2
        vbox_orig1 = wx.BoxSizer(wx.VERTICAL)
        vbox_repl1 = wx.BoxSizer(wx.VERTICAL)

        vbox_orig1.Add(self.old_sym_preview)
        vbox_orig1.AddSpacer(15)
        vbox_orig1.Add(self.desc)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.keywords)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.footprint)

        vbox_repl1.Add(self.new_sym_preview)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_desc)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_keywords)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_footprint)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_source)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_quantity)

        gridbox1.Add(vbox_orig1, 0, wx.ALL)
        gridbox1.Add(vbox_repl1, 0, wx.ALL)

        hbox2.AddSpacer(20)
        hbox2.Add(gridbox1, 1, wx.EXPAND)
        hbox2.AddSpacer(20)

        vbox.Add(hbox1, 1, wx.EXPAND)
        vbox.Add(hbox2,1,wx.EXPAND)

        vbox.AddSpacer(15)

        # REPLACE / CANCEL BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(20)
        btn_more_options = wx.Button(panel, -1, "see more options")
        btn_more_options.Bind(wx.EVT_BUTTON, self.OnSeeMore)
        hbox3.Add(btn_more_options, 0, wx.CENTER)
        hbox3.AddSpacer(50)
        btn_replace = wx.Button(panel,-1, "replace")
        btn_replace.SetDefault()
        hbox3.Add(btn_replace, 0, wx.ALIGN_CENTER)
        btn_replace.Bind(wx.EVT_BUTTON, self.OnReplace)
        hbox3.AddSpacer(12)
        btn_dismiss = wx.Button(panel,-1, "cancel")
        hbox3.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)
        hbox3.AddSpacer(20)
        vbox.Add(hbox3,1, wx.ALIGN_RIGHT)
        vbox.AddSpacer(15)

        panel.SetSizer(vbox)

    def Update(self):
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        o_partname = helper.orig_part_dict["lib_id"]

        self.old_cmpn_lbl.SetLabel(o_partname)
        self.sugg_cmpn_lbl.SetLabel(helper.matched_part_dict["lib_id"])

        o_partname_str = o_partname.split(":")[1]
        n_partname_str = helper.matched_part_dict["lib_id"].split(":")[1]

        # DRAW LIST FOR SUGGESTED SYMBOL FROM LIB UTILS FUNCTION
        self.new_sym_preview.draw_list, bounds = get_sym_elements_for_component(lib_path, n_partname_str)
        width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
        height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

        if width > 0 and height > 0:
            scale = min(200/(width+10), 115/(height+10))

            self.new_sym_preview.scale = scale
            self.new_sym_preview.min_x = bounds['min_x']
            self.new_sym_preview.max_y = bounds['max_y']
            self.new_sym_preview.width = width
            self.new_sym_preview.height = height

        self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)

        # DRAW LIST FOR ORIGINAL SYMBOL FROM DISPATCH

        if 'Symbol Elements' in helper.orig_part_dict.keys():
            self.old_sym_preview.draw_list = helper.orig_part_dict['Symbol Elements']
            if 'Symbol Bounds' in helper.orig_part_dict.keys():
                bounds = helper.orig_part_dict['Symbol Bounds']
                width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
                height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

                if width > 0 and height > 0:
                    scale = min(200/(width+10), 115/(height+10))

                    self.old_sym_preview.scale = scale
                    self.old_sym_preview.min_x = bounds['min_x']
                    self.old_sym_preview.max_y = bounds['max_y']
                    self.old_sym_preview.width = width
                    self.old_sym_preview.height = height
            self.Bind(wx.EVT_PAINT, self.old_sym_preview.OnPaint)

        # DESCRIPTION, KEYWORDS, FOOTPRINT, ETC. TEXT
        # check length to avoid overflow

        desc_text = helper.orig_part_dict["ki_description"]
        if len(desc_text) > 110:
            desc_text = desc_text[:110] + "..."
        kw_text = helper.orig_part_dict["ki_keywords"]
        if len(kw_text) > 28:
            kw_text = kw_text[:28] + "..."
        fp_text = helper.orig_part_dict["Footprint"]
        if len(fp_text) > 26:
            fp_text = fp_text[:26] + "..."

        self.desc.SetLabel(desc_text)
        self.desc.Wrap(200)
        self.keywords.SetLabel("KEYWORDS: " + kw_text)
        self.footprint.SetLabel("FOOTPRINT: " + fp_text)

        s_desc_text = helper.matched_part_dict["ki_description"]
        if len(s_desc_text) > 110:
            s_desc_text = s_desc_text[:110] + "..."

        s_kw_text = helper.matched_part_dict["ki_keywords"]
        if len(s_kw_text) > 28:
            s_kw_text = s_kw_text[:28] + "..."

        s_fp_text = helper.matched_part_dict["Footprint"]
        if len(s_fp_text) > 26:
            s_fp_text = s_fp_text[:26] + "..."

        s_source_text = helper.matched_part_dict["Source"]
        if len(s_source_text) > 30:
            s_source_text = s_source_text[:30] + "..."

        self.n_desc.SetLabel(s_desc_text)
        self.n_desc.Wrap(200)
        self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)
        self.n_footprint.SetLabel("FOOTPRINT: " + s_fp_text)

        self.n_source.SetLabel("SOURCE: " + s_source_text)
        self.n_quantity.SetLabel("QUANTITY: " + helper.matched_part_dict["Quantity"])

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReplace(self, event):
        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnSeeMore(self, event):
        self.Hide()
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/see_ranked", json.dumps(helper.orig_part_dict))
        helper.lock_suggestions = False

class Diff_FP_Notif(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for suggestion notification
        '''

        #NOTIF FRAME STRUCTURE
        super(Diff_FP_Notif, self).__init__(parent, pos=(1000,200), size = (320,100), style=wx.FRAME_NO_TASKBAR|wx.STAY_ON_TOP)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)

        lbl.SetLabel("new ecoEDA suggestion!")

        # DROP IN TEXT + COMPONENT NAME
        self.lbl_type = wx.StaticText(panel, -1, style=wx.ALIGN_LEFT)
        self.lbl_type.SetLabel("different footprint")
        font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.lbl_type.SetFont(font_lbl_type)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(290,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        hbox2.AddSpacer(40)
        hbox2.Add(self.lbl_type, 0, wx.ALIGN_LEFT)

        # ACCEPT / REVIEW BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(40)
        btn_accept = wx.Button(panel, -1, "accept")
        btn_accept.SetDefault()
        btn_accept.Bind(wx.EVT_BUTTON, self.OnReplace)

        hbox3.Add(btn_accept, 0, wx.ALIGN_LEFT)
        btn_review = wx.Button(panel,-1,"review")

        hbox3.AddSpacer(10)
        hbox3.Add(btn_review, 0, wx.ALIGN_LEFT)
        btn_review.Bind(wx.EVT_BUTTON, self.OnReview)
        hbox3.AddSpacer(40)

        vbox.AddSpacer(5)
        vbox.Add(hbox,1,wx.ALIGN_LEFT)
        vbox.Add(hbox2, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)
        vbox.Add(hbox3, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)

        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReview(self, event):
        self.Hide()
        diff_fp_review.Update()
        diff_fp_review.Show()

    def set_component(self, component):
        '''
        modify notification text if the name is too long and resize text
        '''
        if len(component) < 8:
            font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 11:
            font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 15:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:15] + "..."
        self.lbl_type.SetFont(font_lbl_type)
        self.lbl_type.SetLabel("different footprint - " + component)
        client.send_message("/kicad_log", "diff fp for " + component)

    def OnReplace(self, event):
        self.Hide()
        #SEND MESSAGE TO LOCAL SERVER 
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2]
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

class Diff_FP_Review(wx.Frame):
    def __init__(self, parent, title):
        #DIFF FP REVIEW FRAME STRUCTURE
        super(Diff_FP_Review, self).__init__(parent, pos=(500,200), size = (500,380), style=wx.FRAME_NO_TASKBAR|wx.STAY_ON_TOP)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(470,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        #HEADING
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)

        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER_HORIZONTAL)
        font_lbl = wx.Font(24, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("exact match w/ different footprint")
        lbl.Wrap(700)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.AddSpacer(10)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)

        vbox.AddSpacer(10)
        vbox.Add(hbox,1,wx.EXPAND)
        vbox.AddSpacer(10)

        # COMPONENT COMPARISON SECTION

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox = wx.GridSizer(0,2,0,20) # for component comparison

        #top labels for pictures
        orig_lbl = wx.StaticText(panel,-1)
        font_top_lbl = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        orig_lbl.SetFont(font_top_lbl)
        orig_lbl.SetLabel("ORIGINAL")
        sugg_lbl = wx.StaticText(panel,-1)
        sugg_lbl.SetFont(font_top_lbl)
        sugg_lbl.SetLabel("SUGGESTED")

        #component names
        self.old_cmpn_lbl = wx.StaticText(panel,-1, "7805", style = wx.ALIGN_CENTER_HORIZONTAL)
        old_cmpn_font = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.old_cmpn_lbl.SetFont(old_cmpn_font)

        #suggestion
        self.sugg_cmpn_lbl =wx.StaticText(panel,-1, "7805", style = wx.ALIGN_CENTER_HORIZONTAL)
        self.sugg_cmpn_lbl.SetFont(old_cmpn_font)

        #Preview Images
        draw_elements_old = []
        draw_elements_new = []

        self.old_sym_preview = FootprintPreviewPanel(panel, draw_elements_old)
        self.new_sym_preview = FootprintPreviewPanel(panel, draw_elements_new)

        #component details
        self.desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.desc.SetFont(desc_font)
        self.desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.desc.Wrap(200)

        self.keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        keywords_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.keywords.SetFont(keywords_font)
        self.keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.footprint = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.footprint.SetFont(keywords_font)
        self.footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_desc.SetFont(desc_font)
        self.n_desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.n_desc.Wrap(200)

        self.n_keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_keywords.SetFont(keywords_font)
        self.n_keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_footprint = wx.StaticText(panel,-1,style=wx.ALIGN_LEFT)
        self.n_footprint.SetFont(keywords_font)
        self.n_footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_source = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_source.SetFont(keywords_font)
        self.n_source.SetLabel("SOURCE: Lorem ipsum dolor sit amet")

        self.n_quantity = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_quantity.SetFont(keywords_font)
        self.n_quantity.SetLabel("QUANTITY: 1")

        #LAYOUT FOR ALL ELEMENTS
        #vboxes for each column
        vbox_orig = wx.BoxSizer(wx.VERTICAL)
        vbox_repl = wx.BoxSizer(wx.VERTICAL)

        #add to each column
        vbox_orig.Add(orig_lbl)
        vbox_orig.AddSpacer(5)
        vbox_orig.Add(self.old_cmpn_lbl)
        vbox_orig.AddSpacer(10)

        vbox_repl.Add(sugg_lbl)
        vbox_repl.AddSpacer(5)
        vbox_repl.Add(self.sugg_cmpn_lbl)
        vbox_repl.AddSpacer(10)

        #add to grid
        gridbox.Add(vbox_orig, 0, wx.ALL, border=0)
        gridbox.Add(vbox_repl,0, wx.ALL, border=0)

        hbox1.AddSpacer(20)
        hbox1.Add(gridbox, 1, wx.EXPAND)
        hbox1.AddSpacer(20)


        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox1 = wx.GridSizer(0,2,0,20) # for component comparison layer 2

        #vboxes for each column layer 2
        vbox_orig1 = wx.BoxSizer(wx.VERTICAL)
        vbox_repl1 = wx.BoxSizer(wx.VERTICAL)

        vbox_orig1.Add(self.old_sym_preview)
        vbox_orig1.AddSpacer(15)
        vbox_orig1.Add(self.desc)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.keywords)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.footprint)

        vbox_repl1.Add(self.new_sym_preview)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_desc)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_keywords)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_footprint)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_source)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_quantity)

        gridbox1.Add(vbox_orig1, 0, wx.ALL)
        gridbox1.Add(vbox_repl1, 0, wx.ALL)

        hbox2.AddSpacer(20)
        hbox2.Add(gridbox1, 1, wx.EXPAND)
        hbox2.AddSpacer(20)

        vbox.Add(hbox1, 1, wx.EXPAND)
        vbox.Add(hbox2,1,wx.EXPAND)

        vbox.AddSpacer(15)

        # REPLACE / CANCEL BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(20)
        btn_more_options = wx.Button(panel, -1, "see more options")
        btn_more_options.Bind(wx.EVT_BUTTON, self.OnSeeMore)
        hbox3.Add(btn_more_options, 0, wx.CENTER)
        hbox3.AddSpacer(50)
        btn_replace = wx.Button(panel,-1, "replace")
        btn_replace.SetDefault()
        hbox3.Add(btn_replace, 0, wx.ALIGN_CENTER)
        btn_replace.Bind(wx.EVT_BUTTON, self.OnReplace)
        hbox3.AddSpacer(12)
        btn_dismiss = wx.Button(panel,-1, "cancel")
        hbox3.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)
        hbox3.AddSpacer(20)
        vbox.Add(hbox3,1, wx.ALIGN_RIGHT)
        vbox.AddSpacer(15)

        panel.SetSizer(vbox)

    def Update(self):
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        o_partname = helper.orig_part_dict["lib_id"]
        o_reference = helper.orig_part_dict["reference"]

        self.old_cmpn_lbl.SetLabel(o_partname)
        self.sugg_cmpn_lbl.SetLabel(helper.matched_part_dict["lib_id"])

        o_footprint_str = helper.orig_part_dict["Footprint"]
        n_footprint_str = helper.matched_part_dict["Footprint"]

        

        # DRAW LIST FOR SUGGESTED SYMBOL FROM LIB UTILS FUNCTION
        self.new_sym_preview.draw_list, bounds = get_fp_draw_elements(fp_dir, n_footprint_str)
        
        width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
        height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

        if width > 0 and height > 0:
            scale = min(200/(width+10), 115/(height+10))

            self.new_sym_preview.scale = scale
            self.new_sym_preview.min_x = bounds['min_x']
            self.new_sym_preview.min_y = bounds['min_y']
            self.new_sym_preview.width = width
            self.new_sym_preview.height = height

        self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)
        

        
        # DRAW LIST FOR ORIGINAL SYMBOL FROM DISPATCH
        self.old_sym_preview.draw_list, bounds = get_fp_draw_elements(fp_dir, o_footprint_str)
        width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
        height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

        if width > 0 and height > 0:
            scale = min(200/(width+10), 115/(height+10))

            self.old_sym_preview.scale = scale
            self.old_sym_preview.min_x = bounds['min_x']
            self.old_sym_preview.min_y = bounds['min_y']
            self.old_sym_preview.width = width
            self.old_sym_preview.height = height

        self.Bind(wx.EVT_PAINT, self.old_sym_preview.OnPaint)
        
        # DESCRIPTION, KEYWORDS, ETC. TEXT
        # check length to avoid overflow

        desc_text = helper.orig_part_dict["ki_description"]
        if len(desc_text) > 110:
            desc_text = desc_text[:110] + "..."

        kw_text = helper.orig_part_dict["ki_keywords"]
        if len(kw_text) > 28:
            kw_text = kw_text[:28] + "..."

        fp_text = helper.orig_part_dict["Footprint"]
        if len(fp_text) > 26:
            fp_text = fp_text[:26] + "..."

        self.desc.SetLabel(desc_text)
        self.desc.Wrap(200)
        self.keywords.SetLabel("KEYWORDS: " + kw_text)
        self.footprint.SetLabel("FOOTPRINT: " + fp_text)

        s_desc_text = helper.matched_part_dict["ki_description"]
        if len(s_desc_text) > 110:
            s_desc_text = s_desc_text[:110] + "..."

        s_kw_text = helper.matched_part_dict["ki_keywords"]
        if len(s_kw_text) > 28:
            s_kw_text = s_kw_text[:28] + "..."

        s_fp_text = helper.matched_part_dict["Footprint"]
        if len(s_fp_text) > 26:
            s_fp_text = s_fp_text[:26] + "..."

        s_source_text = helper.matched_part_dict["Source"]
        if len(s_source_text) > 30:
            s_source_text = s_source_text[:30] + "..."

        self.n_desc.SetLabel(s_desc_text)
        self.n_desc.Wrap(200)
        self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)
        self.n_footprint.SetLabel("FOOTPRINT: " + s_fp_text)

        self.n_source.SetLabel("SOURCE: " + s_source_text)
        self.n_quantity.SetLabel("QUANTITY: " + helper.matched_part_dict["Quantity"])

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReplace(self, event):
        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnSeeMore(self, event):
        self.Hide()
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/see_ranked", json.dumps(helper.orig_part_dict))
        helper.lock_suggestions = False

class Ranked_Notif(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for suggestion notification
        '''

        #NOTIF FRAME STRUCTURE
        super(Ranked_Notif, self).__init__(parent, pos=(1000,200), size = (320,100), style=wx.FRAME_NO_TASKBAR|wx.STAY_ON_TOP)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)

        lbl.SetLabel("new ecoEDA suggestion!")

        # RANKED SUGGESTIONS TEXT
        self.lbl_type = wx.StaticText(panel, -1, style=wx.ALIGN_LEFT)
        self.lbl_type.SetLabel("ranked matches - COMPONENT_NAME")
        font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.lbl_type.SetFont(font_lbl_type)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(290,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        hbox2.AddSpacer(40)
        hbox2.Add(self.lbl_type, 0, wx.ALIGN_LEFT)

        # REVIEW BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(40)
        btn_review = wx.Button(panel,-1,"review all")

        hbox3.AddSpacer(10)
        hbox3.Add(btn_review, 0, wx.ALIGN_CENTER)
        btn_review.Bind(wx.EVT_BUTTON, self.OnReview)
        hbox3.AddSpacer(40)

        vbox.AddSpacer(5)
        vbox.Add(hbox,1,wx.ALIGN_LEFT)
        vbox.Add(hbox2, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)
        vbox.Add(hbox3, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)

        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "RANKED_NOTIF")
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        helper.reset_vals()
        self.Hide()

    def OnReview(self, event):
        self.Hide()
        ranked_list.Update()
        ranked_list.Show()

    def set_component(self, component):
        '''
        modify notification text if the name is too long and resize text
        '''
        if len(component) < 13:
            font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 16:
            font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 20:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:20] + "..."
        self.lbl_type.SetFont(font_lbl_type)
        self.lbl_type.SetLabel("ranked matches - " + component)
        client.send_message("/kicad_log", "ranked matches for " + component)

class Ranked_List(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for listed suggestions
        '''

        #LIST FRAME STRUCTURE
        super(Ranked_List, self).__init__(parent, pos=(800,200), size = (400,350), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        #ADDITIONAL FILTERS PANEL
        self.filter_panel = Filters_Panel(self)
        self.filter_panel.Position(wx.Point(1280,80), wx.Size(200,200))

        # HEADING
        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER)
        font_lbl = wx.Font(20, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("ranked ecoEDA suggestions")

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(hbox,1,wx.ALIGN_CENTER_VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(390,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        # LIST OF COMPONENTS
        vbox_cmpnts = wx.BoxSizer(wx.VERTICAL)
        lbl_cmpnts = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER)
        lbl_cmpnts.SetFont(wx.Font(10, wx.SWISS, wx.BOLD, wx.BOLD))
        lbl_cmpnts.SetLabel("SUGGESTED COMPONENTS")

        # FILTERS BUTTON
        btn_filters = wx.Button(panel,-1, "[ filter results ]", style=wx.BORDER_NONE)
        btn_filters.Bind(wx.EVT_BUTTON, self.OpenFiltersPanel)

        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(20)
        hbox3.Add(lbl_cmpnts,0,wx.ALIGN_LEFT)
        hbox3.AddSpacer(80)
        hbox3.Add(btn_filters,1,wx.ALIGN_RIGHT)

        vbox_cmpnts.Add(hbox3,1,wx.EXPAND)
        vbox_cmpnts.AddSpacer(10)

        self.components = ['COMPONENT_ONE', 'COMPONENT_TWO', 'COMPONENT_THREE']

        #component 1
        hbox4 = wx.BoxSizer(wx.HORIZONTAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        hbox4.AddSpacer(20)
        hbox4.Add(sbm_logo, wx.ALIGN_LEFT|wx.LEFT, border=0)
        hbox4.AddSpacer(5)
        self.cmpns = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER)

        font_cmpns = wx.Font(15, wx.SWISS, wx.NORMAL, wx.NORMAL)
        self.cmpns.SetFont(font_cmpns)
        self.cmpns.SetLabel(self.components[0])

        self.replace_btn0 = wx.Button(panel, -1, "accept", style=wx.BU_EXACTFIT)
        self.replace_btn0.Bind(wx.EVT_BUTTON, self.OnReplace_1)
        self.review_btn0 = wx.Button(panel, -1, "review", style=wx.BU_EXACTFIT)
        self.review_btn0.Bind(wx.EVT_BUTTON, self.OnReview_1)

        hbox4.Add(self.cmpns, 0, wx.ALIGN_LEFT|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=0)
        hbox4.Add(wx.StaticText(panel), wx.EXPAND)
        hbox4.Add(self.replace_btn0, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox4.AddSpacer(5)
        hbox4.Add(self.review_btn0, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox4.AddSpacer(20)
        vbox_cmpnts.Add(hbox4, 1, wx.ALIGN_CENTER_VERTICAL)

        #dividing line
        line0 = wx.StaticLine(panel)
        line_szr0 = wx.GridBagSizer(1, 1)
        line_szr0.Add(line0, pos=(0, 1), span=(0, 32), flag=wx.EXPAND|wx.BOTTOM, border=10)
        vbox_cmpnts.AddSpacer(5)
        vbox_cmpnts.Add(line_szr0, 1, wx.ALIGN_CENTER_HORIZONTAL)

        # component 2
        hbox5 = wx.BoxSizer(wx.HORIZONTAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        hbox5.AddSpacer(20)
        hbox5.Add(sbm_logo, wx.ALIGN_LEFT|wx.LEFT, border=0)
        hbox5.AddSpacer(5)
        self.cmpns1 = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER)
        font_cmpns = wx.Font(15, wx.SWISS, wx.NORMAL, wx.NORMAL)
        self.cmpns1.SetFont(font_cmpns)
        self.cmpns1.SetLabel(self.components[1])

        self.replace_btn1 = wx.Button(panel, -1, "accept", style=wx.BU_EXACTFIT)
        self.replace_btn1.Bind(wx.EVT_BUTTON, self.OnReplace_2)
        self.review_btn1 = wx.Button(panel, -1, "review", style=wx.BU_EXACTFIT)
        self.review_btn1.Bind(wx.EVT_BUTTON, self.OnReview_2)

        hbox5.Add(self.cmpns1, 0, wx.ALIGN_LEFT|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=0)
        hbox5.Add(wx.StaticText(panel), wx.EXPAND)
        hbox5.Add(self.replace_btn1, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox5.AddSpacer(5)
        hbox5.Add(self.review_btn1, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox5.AddSpacer(20)
        vbox_cmpnts.Add(hbox5,1, wx.ALIGN_CENTER_VERTICAL)
        line1 = wx.StaticLine(panel)
        line_szr1 = wx.GridBagSizer(1, 1)
        line_szr1.Add(line1, pos=(0, 1), span=(0, 32), flag=wx.EXPAND|wx.BOTTOM, border=10)
        vbox_cmpnts.AddSpacer(5)
        vbox_cmpnts.Add(line_szr1, 1, wx.ALIGN_CENTER_HORIZONTAL)

        # component three
        hbox6 = wx.BoxSizer(wx.HORIZONTAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        hbox6.AddSpacer(20)
        hbox6.Add(sbm_logo, wx.ALIGN_LEFT|wx.LEFT, border=0)
        hbox6.AddSpacer(5)
        self.cmpns2 = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER)
        font_cmpns = wx.Font(15, wx.SWISS, wx.NORMAL, wx.NORMAL)
        self.cmpns2.SetFont(font_cmpns)
        self.cmpns2.SetLabel(self.components[2])

        self.replace_btn2 = wx.Button(panel, -1, "accept", style=wx.BU_EXACTFIT)
        self.replace_btn2.Bind(wx.EVT_BUTTON, self.OnReplace_3)
        self.review_btn2 = wx.Button(panel, -1, "review", style=wx.BU_EXACTFIT)
        self.review_btn2.Bind(wx.EVT_BUTTON, self.OnReview_3)

        hbox6.Add(self.cmpns2, 0, wx.ALIGN_CENTER_VERTICAL)
        hbox6.Add(wx.StaticText(panel), wx.EXPAND)
        hbox6.Add(self.replace_btn2, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox6.AddSpacer(5)
        hbox6.Add(self.review_btn2, 1, wx.ALIGN_RIGHT|wx.RIGHT, border=0)
        hbox6.AddSpacer(20)
        vbox_cmpnts.Add(hbox6,1, wx.ALIGN_CENTER_VERTICAL)
        line2 = wx.StaticLine(panel)
        line_szr2 = wx.GridBagSizer(1, 1)
        line_szr2.Add(line2, pos=(0, 1), span=(0, 32), flag=wx.EXPAND|wx.BOTTOM, border=10)
        vbox_cmpnts.AddSpacer(5)
        vbox_cmpnts.Add(line_szr2, 1, wx.ALIGN_CENTER_HORIZONTAL)

        vbox.Add(vbox_cmpnts,1,wx.EXPAND)

        # SEE MORE / IGNORE ALL BUTTONS
        hbox7 = wx.BoxSizer(wx.HORIZONTAL)
        review_others = wx.Button(panel,-1,"see more details/suggestions")
        review_others.SetDefault()
        review_others.Bind(wx.EVT_BUTTON, self.OnReview)

        hbox7.Add(review_others, 0, wx.ALIGN_CENTER)
        hbox7.AddSpacer(30)
        btn_dismiss = wx.Button(panel,-1, "ignore all")
        hbox7.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)

        vbox.Add(hbox7,1, wx.ALIGN_CENTER)


        panel.SetSizer(vbox)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "RANKED LIST")
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        helper.reset_vals()
        self.filter_panel.Hide()
        self.Hide()

    def OnReview(self, event):
        '''
         when see more details button is pressed - initiates ranked review frame with first component
        '''
        self.filter_panel.Hide()
        self.Hide()
        ranked_review.Update()
        if len(helper.sugg_components) > 1:
            ranked_review.combo.SetSelection(0)
            ranked_review.UpdateContent()
        ranked_review.Show()

    def OnReview_1(self, event):
        '''
         when first component's review button is pressed - initiates ranked review frame with first component
        '''
        self.filter_panel.Hide()
        self.Hide()

        ranked_review.Update()
        ranked_review.combo.SetSelection(0)
        ranked_review.UpdateContent()
        ranked_review.Show()

    def OnReview_2(self, event):
        '''
         when second component's review button is pressed - initiates ranked review frame with second component
        '''
        self.filter_panel.Hide()
        self.Hide()

        ranked_review.Update()
        ranked_review.combo.SetSelection(1)
        ranked_review.UpdateContent()
        ranked_review.Show()

    def OnReview_3(self, event):
        '''
         when third component's review button is pressed - initiates ranked review frame with third component
        '''
        self.filter_panel.Hide()
        self.Hide()

        ranked_review.Update()
        ranked_review.combo.SetSelection(2)
        ranked_review.UpdateContent()
        ranked_review.Show()

    def OnReplace_1(self, event):
        '''
         when first component's replace button is pressed - initiates replacement
        '''
        self.filter_panel.Hide()
        #reset filters
        helper.filters = {"dk_sim": True,"val_dist": False,"smd": False,"tht": False}

        self.Hide()

        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "ecoEDA:" + helper.sugg_components[0])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnReplace_2(self, event):
        '''
         when second component's replace button is pressed - initiates replacement
        '''
        self.filter_panel.Hide()
        helper.filters = {"dk_sim": True,"val_dist": False,"smd": False,"tht": False}

        self.Hide()

        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "ecoEDA:" + helper.sugg_components[1])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] #MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnReplace_3(self, event):
        '''
         when third component's replace button is pressed - initiates replacement
        '''
        self.filter_panel.Hide()
        helper.filters = {"dk_sim": True,"val_dist": False,"smd": False,"tht": False}

        self.Hide()

        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "ecoEDA:" + helper.sugg_components[2])
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def set_component_lbl(self, component, lbl):
        '''
        modify text if the name is too long and resize text
        '''
        if len(component) < 24:
            font_lbl_type = wx.Font(15, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 25:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 27:
            font_lbl_type = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:27] + "..."
        lbl.SetFont(font_lbl_type)
        lbl.SetLabel(component)

    def Update(self):
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        partname = helper.orig_part_dict["lib_id"]
        reference = helper.orig_part_dict["reference"]

        self.components = helper.sugg_components

        # LIST OUT COMPONENTS DEPENDING ON NUM OF RANKED SUGGESTION MATCHES
        # ENABLE/DISABLE BUTTONS ACCORDINGLY
        if len(self.components) < 3:
            if len(self.components) == 0:
                self.cmpns.SetLabel("no matches")
                self.cmpns1.SetLabel("")
                self.cmpns2.SetLabel("")

                self.replace_btn0.Disable()
                self.review_btn0.Disable()
                self.replace_btn1.Disable()
                self.review_btn1.Disable()
                self.replace_btn2.Disable()
                self.review_btn2.Disable()

            elif len(self.components) == 1:
                self.set_component_lbl(self.components[0], self.cmpns)
                self.cmpns1.SetLabel("")
                self.cmpns2.SetLabel("")

                self.replace_btn1.Disable()
                self.review_btn1.Disable()
                self.replace_btn2.Disable()
                self.review_btn2.Disable()

            elif len(self.components) == 2:
                self.set_component_lbl(self.components[0], self.cmpns)
                self.set_component_lbl(self.components[1], self.cmpns1)
                self.cmpns2.SetLabel("")

                self.replace_btn2.Disable()
                self.review_btn2.Disable()
        else:
            self.set_component_lbl(self.components[0], self.cmpns)
            self.set_component_lbl(self.components[1], self.cmpns1)
            self.set_component_lbl(self.components[2], self.cmpns2)
            self.replace_btn0.Enable()
            self.review_btn0.Enable()
            self.replace_btn1.Enable()
            self.review_btn1.Enable()
            self.replace_btn2.Enable()
            self.review_btn2.Enable()

    def OpenFiltersPanel(self, event):
        '''
            Shows filters UI
        '''
        self.filter_panel.OpenFiltersUpdate()
        self.filter_panel.Show()

class Ranked_Review(wx.Frame):
    def __init__(self, parent, title):
        #RANKED REVIEW FRAME STRUCTURE
        super(Ranked_Review, self).__init__(parent, pos=(500,200), size = (500,420), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(520,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        #FILTERS PANEL
        self.filter_panel = Filters_Panel(self)
        self.filter_panel.Position(wx.Point(1100,120), wx.Size(200,200))

        #HEADING
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)

        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER_HORIZONTAL)
        font_lbl = wx.Font(24, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("review ranked suggestions")
        lbl.Wrap(700)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)

        vbox.AddSpacer(10)
        vbox.Add(hbox,1,wx.EXPAND)
        vbox.AddSpacer(10)

        # COMPONENT COMPARISON SECTION

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox = wx.GridSizer(0,2,0,20) # for component comparison

        #top labels for components
        orig = wx.StaticText(panel,-1)
        font_orig = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        orig.SetFont(font_orig)
        orig.SetLabel("ORIGINAL")
        suggested = wx.StaticText(panel,-1)
        font_suggested = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        suggested.SetFont(font_suggested)
        suggested.SetLabel("SUGGESTED")

        #component names
        self.old_cmpn_lbl = wx.StaticText(panel,-1, "ORIGINAL COMPONENT", style = wx.ALIGN_CENTER_HORIZONTAL)
        old_cmpn_font = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.old_cmpn_lbl.SetFont(old_cmpn_font)

        #suggestion Options
        self.options = ['1. SUGGESTED COMPONENT', '2. SUGGESTED COMPONENT', '3. SUGGESTED COMPONENT', '4. SUGGESTED COMPONENT']
        self.combo = wx.ComboBox(panel,choices = self.options,size=wx.Size(200,24))

        #Preview Images
        draw_elements_old = []
        draw_elements_new = [] #filled on Update

        self.old_sym_preview = SymbolPreviewPanel(panel, draw_elements_old)
        self.new_sym_preview = SymbolPreviewPanel(panel, draw_elements_new)

        #component details
        self.desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.desc.SetFont(desc_font)
        self.desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.desc.Wrap(200)

        self.keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        keywords_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.keywords.SetFont(keywords_font)
        self.keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.footprint = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.footprint.SetFont(keywords_font)
        self.footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_desc.SetFont(desc_font)
        self.n_desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.n_desc.Wrap(200)

        self.n_keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_keywords.SetFont(keywords_font)
        self.n_keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_footprint = wx.StaticText(panel,-1,style=wx.ALIGN_LEFT)
        self.n_footprint.SetFont(keywords_font)
        self.n_footprint.SetLabel("FOOTPRINT: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_source = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_source.SetFont(keywords_font)
        self.n_source.SetLabel("SOURCE: Lorem ipsum dolor sit amet")

        self.n_quantity = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_quantity.SetFont(keywords_font)
        self.n_quantity.SetLabel("QUANTITY: 1")

        #LAYOUT FOR ALL ELEMENTS
        #vboxes for each column
        vbox_orig = wx.BoxSizer(wx.VERTICAL)
        vbox_repl = wx.BoxSizer(wx.VERTICAL)

        #add to each column
        vbox_orig.Add(orig)
        vbox_orig.AddSpacer(5)
        vbox_orig.Add(self.old_cmpn_lbl)
        vbox_orig.AddSpacer(10)

        vbox_repl.Add(suggested)
        vbox_repl.AddSpacer(5)
        vbox_repl.Add(self.combo)
        vbox_repl.AddSpacer(10)

        #filter button (not in grid)
        btn_filters = wx.Button(panel,-1, "[ filter results ]", style=wx.BORDER_NONE, pos=wx.Point(380,62))
        btn_filters.Bind(wx.EVT_BUTTON, self.OpenFiltersPanel)

        #add to grid
        gridbox.Add(vbox_orig, 0, wx.ALL, border=0)
        gridbox.Add(vbox_repl,0, wx.ALL, border=0)

        hbox1.AddSpacer(20)
        hbox1.Add(gridbox, 1, wx.EXPAND)
        hbox1.AddSpacer(20)


        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox1 = wx.GridSizer(0,2,0,20) # for component comparison layer 2

        #vboxes for each column layer 2
        vbox_orig1 = wx.BoxSizer(wx.VERTICAL)
        vbox_repl1 = wx.BoxSizer(wx.VERTICAL)

        vbox_orig1.Add(self.old_sym_preview)
        vbox_orig1.AddSpacer(15)
        vbox_orig1.Add(self.desc)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.keywords)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.footprint)

        vbox_repl1.Add(self.new_sym_preview)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_desc)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_keywords)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_footprint)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_source)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_quantity)

        gridbox1.Add(vbox_orig1, 0, wx.ALL)
        gridbox1.Add(vbox_repl1, 0, wx.ALL)

        hbox2.AddSpacer(20)
        hbox2.Add(gridbox1, 1, wx.EXPAND)
        hbox2.AddSpacer(20)

        vbox.Add(hbox1, 1, wx.EXPAND)
        vbox.Add(hbox2,1,wx.EXPAND)

        vbox.AddSpacer(15)

        # REPLACE / CANCEL BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        btn_replace = wx.Button(panel,-1, "accept selected")
        btn_replace.SetDefault()
        hbox3.Add(btn_replace, 0, wx.ALIGN_CENTER)
        btn_replace.Bind(wx.EVT_BUTTON, self.OnReplace)
        hbox3.AddSpacer(12)
        btn_dismiss = wx.Button(panel,-1, "cancel")
        hbox3.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)
        hbox3.AddSpacer(20)
        vbox.Add(hbox3,1, wx.ALIGN_RIGHT)

        panel.SetSizer(vbox)

    def OnReplace(self, event):
        # Make sure filters panel is closed
        self.filter_panel.Hide()
        helper.filters = {"dk_sim": True,"val_dist": False,"smd": False,"tht": False}

        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "ecoEDA:" + helper.sel_component)
        client.send_message("/o_cmpn", partname)
        client.send_message("/run", part_id)
        helper.reset_vals()
        client.send_message("/update_dict", part_id)

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2]
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)


    def Update(self):
        '''
            only called at beginning to update information related to original component
        '''
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        o_partname = helper.orig_part_dict["lib_id"]

        self.old_cmpn_lbl.SetLabel(o_partname)
        self.options = helper.sugg_components
        self.combo.Clear()
        self.combo.AppendItems(self.options)

        o_partname_str = o_partname.split(":")[1]

        # DRAW LIST FOR ORIGINAL SYMBOL FROM DISPATCH
        if 'Symbol Elements' in helper.orig_part_dict.keys():
            self.old_sym_preview.draw_list = helper.orig_part_dict['Symbol Elements']
            if 'Symbol Bounds' in helper.orig_part_dict.keys():
                bounds = helper.orig_part_dict['Symbol Bounds']
                width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
                height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

                if width > 0 and height > 0:
                    scale = min(200/(width+10), 115/(height+10))

                    self.old_sym_preview.scale = scale
                    self.old_sym_preview.min_x = bounds['min_x']
                    self.old_sym_preview.max_y = bounds['max_y']
                    self.old_sym_preview.width = width
                    self.old_sym_preview.height = height
            self.Bind(wx.EVT_PAINT, self.old_sym_preview.OnPaint)
        
        # DESCRIPTION, KEYWORDS, FOOTPRINT, ETC. TEXT
        # check length to avoid overflow

        desc_text = helper.orig_part_dict["ki_description"]
        if len(desc_text) > 110:
            desc_text = desc_text[:110] + "..."
        kw_text = helper.orig_part_dict["ki_keywords"]
        if len(kw_text) > 28:
            kw_text = kw_text[:28] + "..."
        fp_text = helper.orig_part_dict["Footprint"]
        if len(fp_text) > 26:
            fp_text = fp_text[:26] + "..."

        self.desc.SetLabel(desc_text)
        self.desc.Wrap(200)
        self.keywords.SetLabel("KEYWORDS: " + kw_text)
        self.footprint.SetLabel("FOOTPRINT: " + fp_text)

        self.combo.Bind(wx.EVT_COMBOBOX, self.OnCombo)

    def OnCombo(self, event):
        '''
            handles event of when combo box is changed

        '''

        comp = self.combo.GetStringSelection()

        if comp == "":
            self.new_sym_preview.draw_list = []
            self.new_sym_preview.Refresh()
        else:
            self.new_sym_preview.draw_list, bounds = get_sym_elements_for_component(lib_path, comp)
            width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
            height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

            if width > 0 and height > 0:
                scale = min(200/(width+10), 115/(height+10))

                self.new_sym_preview.scale = scale
                self.new_sym_preview.min_x = bounds['min_x']
                self.new_sym_preview.max_y = bounds['max_y']
                self.new_sym_preview.width = width
                self.new_sym_preview.height = height


            self.new_sym_preview.Refresh()

            helper.sel_component = comp
            
            s_desc_text = helper.suggestions_dict[comp]["ki_description"]
            if len(s_desc_text) > 110:
                s_desc_text = s_desc_text[:110] + "..."

            s_kw_text = helper.suggestions_dict[comp]["ki_keywords"]
            if len(s_kw_text) > 28:
                s_kw_text = s_kw_text[:28] + "..."


            s_fp_text = helper.suggestions_dict[comp]["Footprint"]
            if len(s_fp_text) > 26:
                s_fp_text = s_fp_text[:26] + "..."

            s_source_text = helper.suggestions_dict[comp]["Source"]
            if len(s_source_text) > 30:
                s_source_text = s_source_text[:30] + "..."

            self.n_desc.SetLabel(s_desc_text)
            self.n_desc.Wrap(200)
            self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)

            self.n_footprint.SetLabel("FOOTPRINT: " + s_fp_text)
            

            self.n_source.SetLabel("SOURCE: " + s_source_text)
            self.n_quantity.SetLabel("QUANTITY: " + helper.suggestions_dict[comp]["Quantity"])

    def UpdateContent(self):
        '''
            called when combo box is pre-set to a value
        '''
        comp = self.combo.GetStringSelection()
        if comp == "":
            self.new_sym_preview.draw_list = []
            self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)
        else:
            self.new_sym_preview.draw_list, bounds = get_sym_elements_for_component(lib_path, comp)
            width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
            height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

            if width > 0 and height > 0:
                scale = min(200/(width+10), 115/(height+10))

                self.new_sym_preview.scale = scale
                self.new_sym_preview.min_x = bounds['min_x']
                self.new_sym_preview.max_y = bounds['max_y']
                self.new_sym_preview.width = width
                self.new_sym_preview.height = height

            self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)

            helper.sel_component = comp
            
            s_desc_text = helper.suggestions_dict[comp]["ki_description"]
            if len(s_desc_text) > 110:
                s_desc_text = s_desc_text[:110] + "..."

            s_kw_text = helper.suggestions_dict[comp]["ki_keywords"]
            if len(s_kw_text) > 28:
                s_kw_text = s_kw_text[:28] + "..."


            s_fp_text = helper.suggestions_dict[comp]["Footprint"]
            if len(s_fp_text) > 26:
                s_fp_text = s_fp_text[:26] + "..."

            s_source_text = helper.suggestions_dict[comp]["Source"]
            if len(s_source_text) > 30:
                s_source_text = s_source_text[:30] + "..."

            self.n_desc.SetLabel(s_desc_text)
            self.n_desc.Wrap(200)
            self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)

            self.n_footprint.SetLabel("FOOTPRINT: " + s_fp_text)
            

            self.n_source.SetLabel("SOURCE: " + s_source_text)
            self.n_quantity.SetLabel("QUANTITY: " + helper.suggestions_dict[comp]["Quantity"])


    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", "ranked review"+ self.combo.GetStringSelection())
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.filter_panel.Hide()
        self.Hide()
        self.combo.Clear()
        helper.sugg_components.clear()
        self.options.clear()

    def OpenFiltersPanel(self, event):
        self.filter_panel.OpenFiltersUpdate()
        self.filter_panel.Show()

class Subcircuit_Notif(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for suggestion notification
        '''

        #NOTIF FRAME STRUCTURE
        super(Subcircuit_Notif, self).__init__(parent, pos=(1000,200), size = (320,100), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)

        lbl.SetLabel("new ecoEDA suggestion!")

        # SUBCIRCUIT SUGGESTIONS TEXT
        self.lbl_type = wx.StaticText(panel, -1, style=wx.ALIGN_LEFT)
        self.lbl_type.SetLabel("subcircuit - COMPONENT_NAME")
        font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.lbl_type.SetFont(font_lbl_type)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(390,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        hbox2 = wx.BoxSizer(wx.HORIZONTAL)

        hbox2.AddSpacer(40)
        hbox2.Add(self.lbl_type, 0, wx.ALIGN_LEFT)

        # ACCEPT/REVIEW BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(40)
        btn_accept = wx.Button(panel, -1, "accept")
        btn_accept.SetDefault()
        btn_accept.Bind(wx.EVT_BUTTON, self.OnReplace)

        hbox3.Add(btn_accept, 0, wx.ALIGN_LEFT)
        btn_review = wx.Button(panel,-1,"review")
        hbox3.AddSpacer(10)
        hbox3.Add(btn_review, 0, wx.ALIGN_LEFT)
        btn_review.Bind(wx.EVT_BUTTON, self.OnReview)
        hbox3.AddSpacer(40)

        vbox.AddSpacer(5)
        vbox.Add(hbox,1,wx.ALIGN_LEFT)
        vbox.Add(hbox2, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)
        vbox.Add(hbox3, 1, wx.ALIGN_LEFT)
        vbox.AddSpacer(5)

        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReview(self, event):
        self.Hide()
        subcircuit_review.Update()
        subcircuit_review.Show()

    def set_component(self, component):
        '''
        modify notification text if the name is too long and resize text
        '''
        if len(component) < 17:
            font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 20:
            font_lbl_type = wx.Font(16, wx.SWISS, wx.BOLD, wx.NORMAL)
        elif len(component) < 24:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
        else:
            font_lbl_type = wx.Font(14, wx.SWISS, wx.BOLD, wx.NORMAL)
            component = component[:24] + "..."
        self.lbl_type.SetFont(font_lbl_type)
        self.lbl_type.SetLabel("subcircuit - " + component)
        client.send_message("/kicad_log", "subcircuit for " + component)

    def OnReplace(self, event):
        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/subcircuit_run", part_id)
        helper.reset_vals()

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2]
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

class Subcircuit_Review(wx.Frame):
    def __init__(self, parent, title):
        #SUBCIRCUIT REVIEW FRAME STRUCTURE
        super(Subcircuit_Review, self).__init__(parent, pos=(500,200), size = (500,380), style=wx.FRAME_NO_TASKBAR)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)

        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(470,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        #HEADING
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG)
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)

        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_CENTER_HORIZONTAL)
        font_lbl = wx.Font(24, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl)
        lbl.SetLabel("review subcircuit match")
        lbl.Wrap(700)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.AddSpacer(20)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER)
        hbox.AddSpacer(10)
        hbox.Add(lbl,0, wx.ALIGN_CENTER_VERTICAL)

        vbox.AddSpacer(10)
        vbox.Add(hbox,1,wx.EXPAND)
        vbox.AddSpacer(10)

        # COMPONENT COMPARISON SECTION

        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox = wx.GridSizer(0,2,0,20) # for component comparison

        #top labels for pictures
        orig_lbl = wx.StaticText(panel,-1)
        font_top_lbl = wx.Font(16, wx.SWISS, wx.BOLD, wx.BOLD)
        orig_lbl.SetFont(font_top_lbl)
        orig_lbl.SetLabel("ORIGINAL")
        sugg_lbl = wx.StaticText(panel,-1)
        sugg_lbl.SetFont(font_top_lbl)
        sugg_lbl.SetLabel("SUGGESTED")

        #component names
        self.old_cmpn_lbl = wx.StaticText(panel,-1, "ORIGINAL COMPONENT NAME", style = wx.ALIGN_CENTER_HORIZONTAL)
        old_cmpn_font = wx.Font(12, wx.SWISS, wx.BOLD, wx.NORMAL)
        self.old_cmpn_lbl.SetFont(old_cmpn_font)

        #suggestion
        self.sugg_cmpn_lbl =wx.StaticText(panel,-1, "SUGGESTED SUBCIRCUIT NAME", style = wx.ALIGN_CENTER_HORIZONTAL)
        self.sugg_cmpn_lbl.SetFont(old_cmpn_font)

        #Preview Images
        draw_elements_old = []
        draw_elements_new = [] #these get filled on Update

        self.old_sym_preview = SymbolPreviewPanel(panel, draw_elements_old)
        self.new_sym_preview = SymbolPreviewPanel(panel, draw_elements_new)

        #component details
        self.desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.desc.SetFont(desc_font)
        self.desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.desc.Wrap(200)

        self.keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        keywords_font = wx.Font(10, wx.DEFAULT, wx.BOLD, wx.NORMAL)
        self.keywords.SetFont(keywords_font)
        self.keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_desc = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_desc.SetFont(desc_font)
        self.n_desc.SetLabel("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.n_desc.Wrap(200)

        self.n_keywords = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_keywords.SetFont(keywords_font)
        self.n_keywords.SetLabel("KEYWORDS: Lorem ipsum dolor sit amet, consectetur adipiscing")

        self.n_source = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_source.SetFont(keywords_font)
        self.n_source.SetLabel("SOURCE: Lorem ipsum dolor sit amet")

        self.n_quantity = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        self.n_quantity.SetFont(keywords_font)
        self.n_quantity.SetLabel("QUANTITY: 1")

        #LAYOUT FOR ALL ELEMENTS
        #vboxes for each column
        vbox_orig = wx.BoxSizer(wx.VERTICAL)
        vbox_repl = wx.BoxSizer(wx.VERTICAL)

        #add to each column
        vbox_orig.Add(orig_lbl)
        vbox_orig.AddSpacer(5)
        vbox_orig.Add(self.old_cmpn_lbl)
        vbox_orig.AddSpacer(10)

        vbox_repl.Add(sugg_lbl)
        vbox_repl.AddSpacer(5)
        vbox_repl.Add(self.sugg_cmpn_lbl)
        vbox_repl.AddSpacer(10)

        #add to grid
        gridbox.Add(vbox_orig, 0, wx.ALL, border=0)
        gridbox.Add(vbox_repl,0, wx.ALL, border=0)

        hbox1.AddSpacer(20)
        hbox1.Add(gridbox, 1, wx.EXPAND)
        hbox1.AddSpacer(20)


        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        gridbox1 = wx.GridSizer(0,2,0,20) # for component comparison layer 2

        #vboxes for each column layer 2
        vbox_orig1 = wx.BoxSizer(wx.VERTICAL)
        vbox_repl1 = wx.BoxSizer(wx.VERTICAL)

        vbox_orig1.Add(self.old_sym_preview)
        vbox_orig1.AddSpacer(15)
        vbox_orig1.Add(self.desc)
        vbox_orig1.AddSpacer(5)
        vbox_orig1.Add(self.keywords)

        vbox_repl1.Add(self.new_sym_preview)
        vbox_repl1.AddSpacer(15)
        vbox_repl1.Add(self.n_desc)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_keywords)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_source)
        vbox_repl1.AddSpacer(5)
        vbox_repl1.Add(self.n_quantity)

        gridbox1.Add(vbox_orig1, 0, wx.ALL)
        gridbox1.Add(vbox_repl1, 0, wx.ALL)

        hbox2.AddSpacer(20)
        hbox2.Add(gridbox1, 1, wx.EXPAND)
        hbox2.AddSpacer(20)

        vbox.Add(hbox1, 1, wx.EXPAND)
        vbox.Add(hbox2,1,wx.EXPAND)

        vbox.AddSpacer(15)

        # REPLACE / CANCEL BUTTONS
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3.AddSpacer(20)
        btn_more_options = wx.Button(panel, -1, "see more options")
        btn_more_options.Bind(wx.EVT_BUTTON, self.OnSeeMore)
        hbox3.Add(btn_more_options, 0, wx.CENTER)
        hbox3.AddSpacer(50)
        btn_replace = wx.Button(panel,-1, "replace")
        btn_replace.SetDefault()
        hbox3.Add(btn_replace, 0, wx.ALIGN_CENTER)
        btn_replace.Bind(wx.EVT_BUTTON, self.OnReplace)
        hbox3.AddSpacer(12)
        btn_dismiss = wx.Button(panel,-1, "cancel")
        hbox3.Add(btn_dismiss, 0, wx.ALIGN_CENTER)
        btn_dismiss.Bind(wx.EVT_BUTTON, self.OnDismiss)
        hbox3.AddSpacer(20)
        vbox.Add(hbox3,1, wx.ALIGN_RIGHT)
        vbox.AddSpacer(15)

        panel.SetSizer(vbox)

    def Update(self):
        #USE UPDATED PARTS INFORMATION IN HELPER TO UPDATE UI
        o_partname = helper.orig_part_dict["lib_id"]

        self.old_cmpn_lbl.SetLabel(o_partname)
        self.sugg_cmpn_lbl.SetLabel(helper.matched_part_dict["lib_id"])

        o_partname_str = o_partname.split(":")[1]
        n_partname_str = helper.matched_part_dict["lib_id"].split("Subcircuit-")[1]

        # DRAW LIST FOR SUGGESTED SYMBOL FROM LIB UTILS FUNCTION
        self.new_sym_preview.draw_list, bounds = get_subcircuit_draw_elements(ecoEDA_dir, n_partname_str)
        width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
        height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

        if width > 0 and height > 0:
            scale = min(200/(width+10), 115/(height+10))

            self.new_sym_preview.scale = scale
            self.new_sym_preview.min_x = bounds['min_x']
            self.new_sym_preview.max_y = bounds['max_y']
            self.new_sym_preview.width = width
            self.new_sym_preview.height = height

        self.Bind(wx.EVT_PAINT, self.new_sym_preview.OnPaint)

        # DRAW LIST FOR ORIGINAL SYMBOL FROM DISPATCH

        if 'Symbol Elements' in helper.orig_part_dict.keys():
            self.old_sym_preview.draw_list = helper.orig_part_dict['Symbol Elements']
            if 'Symbol Bounds' in helper.orig_part_dict.keys():
                bounds = helper.orig_part_dict['Symbol Bounds']
                width = abs(int((bounds['max_x'] - bounds['min_x'])*10))
                height = abs(int((bounds['max_y'] - bounds['min_y'])*10))

                if width > 0 and height > 0:
                    scale = min(200/(width+10), 115/(height+10))

                    self.old_sym_preview.scale = scale
                    self.old_sym_preview.min_x = bounds['min_x']
                    self.old_sym_preview.max_y = bounds['max_y']
                    self.old_sym_preview.width = width
                    self.old_sym_preview.height = height
            self.Bind(wx.EVT_PAINT, self.old_sym_preview.OnPaint)

        # DESCRIPTION, KEYWORDS, FOOTPRINT, ETC. TEXT
        # check length to avoid overflow

        desc_text = helper.orig_part_dict["ki_description"]
        if len(desc_text) > 110:
            desc_text = desc_text[:110] + "..."
        kw_text = helper.orig_part_dict["ki_keywords"]
        if len(kw_text) > 28:
            kw_text = kw_text[:28] + "..."

        self.desc.SetLabel(desc_text)
        self.desc.Wrap(200)
        self.keywords.SetLabel("KEYWORDS: " + kw_text)

        s_desc_text = helper.matched_part_dict["ki_description"]
        if len(s_desc_text) > 110:
            s_desc_text = s_desc_text[:110] + "..."

        s_kw_text = helper.matched_part_dict["ki_keywords"]
        if len(s_kw_text) > 28:
            s_kw_text = s_kw_text[:28] + "..."

        s_source_text = helper.matched_part_dict["Source"]
        if len(s_source_text) > 30:
            s_source_text = s_source_text[:30] + "..."

        self.n_desc.SetLabel(s_desc_text)
        self.n_desc.Wrap(200)
        self.n_keywords.SetLabel("KEYWORDS: " + s_kw_text)

        self.n_source.SetLabel("SOURCE: " + s_source_text)
        self.n_quantity.SetLabel("QUANTITY: " + helper.matched_part_dict["Quantity"])

    def OnDismiss(self, event):
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/dismiss_suggestion", part_id)
        helper.lock_suggestions = False
        self.Hide()

    def OnReplace(self, event):
        # SEND MESSAGE TO LOCAL CLIENT TO APPLY REPLACEMENT
        self.Hide()
        partname = helper.orig_part_dict["lib_id"]
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/n_cmpn", helper.matched_part_dict["lib_id"])
        client.send_message("/o_cmpn", partname)
        client.send_message("/subcircuit_run", part_id)
        helper.reset_vals()

        # PRESS REVERT BUTTON IN KICAD
        frame = wx.FindWindowByName("SchematicFrame")
        filemenu = frame.MenuBar.GetMenu(0)
        revertitem = filemenu.GetMenuItems()[2] # MAY NEED TO CHANGE
        revert_event = wx.CommandEvent(wx.EVT_MENU.typeId, revertitem.GetId())
        time.sleep(2)
        filemenu.ProcessEvent(revert_event)

    def OnSeeMore(self, event):
        self.Hide()
        part_id = helper.orig_part_dict["uuid"]
        client.send_message("/see_ranked", json.dumps(helper.orig_part_dict))
        helper.lock_suggestions = False

class Filters_Panel(wx.PopupWindow):
    def __init__(self, parent):
        wx.PopupWindow.__init__(self, parent=parent)
        panel = wx.Panel(self, style=wx.BORDER_DEFAULT)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        self.SetSize(220,150)
        panel.SetSize(220,150)

        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(190,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)

        sort_by_lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        sort_by_lbl.SetLabel("SORT BY:")
        sort_by_lbl.SetFont(wx.Font(10, wx.SWISS, wx.BOLD, wx.BOLD))
        self.desc_match_cb = wx.CheckBox( panel, wx.ID_ANY, "name, desc, keywords", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.desc_match_cb.SetValue(True)
        self.value_cb = wx.CheckBox( panel, wx.ID_ANY, u"value distance", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.value_cb.SetValue(False)

        show_only_lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        show_only_lbl.SetLabel("SHOW ONLY:")
        show_only_lbl.SetFont(wx.Font(10, wx.SWISS, wx.BOLD, wx.BOLD))
        self.smd_cb = wx.CheckBox( panel, wx.ID_ANY, u"SMD", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.smd_cb.SetValue(False)
        self.tht_cb = wx.CheckBox( panel, wx.ID_ANY, u"THT", wx.DefaultPosition, wx.DefaultSize, 0 )
        self.tht_cb.SetValue(False)

        btn_update = wx.Button(panel, -1, "update results with filters")
        btn_update.Bind(wx.EVT_BUTTON, self.OnUpdate)
        btn_update.SetDefault()

        m_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(sort_by_lbl, 0, wx.EXPAND, 10)
        sizer.Add(self.desc_match_cb, 0, wx.EXPAND, 10)
        sizer.Add(self.value_cb, 0, wx.EXPAND, 10)
        sizer.AddSpacer(10)
        sizer.Add(show_only_lbl, 0, wx.EXPAND, 10)
        sizer.Add(self.smd_cb, 0, wx.EXPAND, 10)
        sizer.Add(self.tht_cb, 0, wx.EXPAND, 10)
        sizer.AddSpacer(10)
        sizer.Add(btn_update, 0, wx.EXPAND, 0)

        m_sizer.AddSpacer(10)
        m_sizer.Add(sizer, 0, wx.EXPAND, 10)
        m_sizer.AddSpacer(10)

        self.SetSizer(m_sizer)

    def OnDismiss(self, event):
        self.Hide()

    def OnUpdate(self, event):
        helper.filters = {"dk_sim": self.desc_match_cb.GetValue(),
                   "val_dist": self.value_cb.GetValue(),
                   "smd": self.smd_cb.GetValue(),
                   "tht": self.tht_cb.GetValue()}
        helper.filter_suggestions()
        ranked_list.Update()
        ranked_review.Update()
        ranked_review.combo.SetSelection(0)
        ranked_review.UpdateContent()
        self.Hide()

    def OpenFiltersUpdate(self):
        self.desc_match_cb.SetValue(helper.filters["dk_sim"])
        self.value_cb.SetValue(helper.filters["val_dist"])
        self.smd_cb.SetValue(helper.filters["smd"])
        self.tht_cb.SetValue(helper.filters["tht"])

class SymbolPreviewPanel(wx.Panel):
    def __init__(self, parent, draw_elements):
        wx.Panel.__init__(self,parent,size=(200,115))
        self.SetOwnBackgroundColour(wx.Colour(245,244,239))
        self.InitUI()
        self.draw_list = draw_elements
        self.min_x = 0
        self.width = 0
        self.max_y = 0
        self.height = 0
        self.scale = 1

    def InitUI(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Show(True)

    def convert_vals(self,val):
        new_value = int((val*10))
        if self.min_x < 0:
            new_value += int(self.min_x * -10)
        if self.width > 0:
            new_value += int(((200/self.scale) - self.width) / 2)
        return new_value

    def convert_y_vals(self,val):
        new_value = int((val*-10))
        if self.max_y > 0:
            new_value += int(self.max_y * 10)
        if self.height > 0:
            new_value += int(((115/self.scale) - self.height) / 2)
        return new_value

    def multiply_vals(self,val):
        return int(val*10)

    #adapted from https://www.geeksforgeeks.org/equation-of-circle-when-three-points-on-the-circle-are-given/
    def get_center(self,x1,y1,x2,y2,x3,y3):
        x12 = x1 - x2;
        x13 = x1 - x3;

        y12 = y1 - y2;
        y13 = y1 - y3;

        y31 = y3 - y1;
        y21 = y2 - y1;

        x31 = x3 - x1;
        x21 = x2 - x1;

        # x1^2 - x3^2
        sx13 = pow(x1, 2) - pow(x3, 2);

        # y1^2 - y3^2
        sy13 = pow(y1, 2) - pow(y3, 2);

        sx21 = pow(x2, 2) - pow(x1, 2);
        sy21 = pow(y2, 2) - pow(y1, 2);

        f = (((sx13) * (x12) + (sy13) *
              (x12) + (sx21) * (x13) +
              (sy21) * (x13)) // (2 *
              ((y31) * (x12) - (y21) * (x13))));

        g = (((sx13) * (y12) + (sy13) * (y12) +
              (sx21) * (y13) + (sy21) * (y13)) //
              (2 * ((x31) * (y12) - (x21) * (y13))));


        # eqn of circle be x^2 + y^2 + 2*g*x + 2*f*y + c = 0
        # where centre is (h = -g, k = -f) and
        # radius r as r^2 = h^2 + k^2 - c
        cx = -g;
        cy = -f;

        return cx,cy

    def OnPaint(self, e):
       dc = wx.PaintDC(self)
       brush = wx.Brush(wx.Colour(245,244,239))
       dc.SetUserScale(self.scale,self.scale)
       dc.SetBackground(brush)
       dc.SetTextForeground(wx.Colour(0,100,100))

       dc.SetPen(wx.Pen(wx.Colour(255,0,0)))
       dc.SetBrush(wx.Brush(wx.Colour(255,0,0), style=wx.BRUSHSTYLE_TRANSPARENT))
       dc.SetPen(wx.Pen(wx.Colour(169,0,0)))
       for element in self.draw_list:
           dc.SetPen(wx.Pen(wx.Colour(169,0,0), width=1))
           dc.SetBrush(wx.Brush(wx.Colour(255,0,0), style=wx.BRUSHSTYLE_TRANSPARENT))

           if list(element)[0] == 'arc':
               dc.SetPen(wx.Pen(wx.Colour(169,0,0), width=2))
               elem_vals = element['arc']
               mx = self.convert_vals(elem_vals['mx'])
               my = self.convert_y_vals(elem_vals['my'])
               sx = self.convert_vals(elem_vals['sx'])
               sy = self.convert_y_vals(elem_vals['sy'])
               ex = self.convert_vals(elem_vals['ex'])
               ey = self.convert_y_vals(elem_vals['ey'])
               cx,cy = self.get_center(ex,ey,mx,my,sx,sy)
               
               if mx > sx and my > sy:
                   dc.DrawArc(sx,sy, ex,ey, cx,cy)
               elif mx > sx and my < sy:
                   dc.DrawArc(sx,sy, ex,ey, cx,cy)
               elif mx < sx and my > sy:
                   dc.DrawArc(sx,sy, ex,ey, cx,cy)
               else:
                   dc.DrawArc(ex,ey,sx,sy,cx,cy)
           if list(element)[0] == 'circle':
               elem_vals = element['circle']
               dc.DrawCircle(self.convert_vals(elem_vals['cx']),self.convert_y_vals(elem_vals['cy']),
                             self.multiply_vals(elem_vals['r']) )
           if list(element)[0] == 'rectangle':
               dc.SetPen(wx.Pen(wx.Colour(169,0,0), width=2))
               elem_vals = element['rectangle']

               sx = self.convert_vals(elem_vals['sx'])
               sy = self.convert_y_vals(elem_vals['sy'])
               ex = self.convert_vals(elem_vals['ex'])
               ey = self.convert_y_vals(elem_vals['ey'])
               width = abs(elem_vals['ex'] - elem_vals['sx'])
               height = abs(elem_vals['ey'] - elem_vals['sy'])
               if ex < sx:
                   sx = ex
               if ey < sy:
                   sy = ey
               if elem_vals['fill'] == 'background':
                   dc.SetBrush(wx.Brush(wx.Colour(255,255,194)))
               else:
                   dc.SetBrush(wx.Brush(wx.Colour(255,0,0), style=wx.BRUSHSTYLE_TRANSPARENT))
               dc.DrawRectangle(sx, sy,self.multiply_vals(width), self.multiply_vals(height))
           if list(element)[0] == 'pin':
               elem_vals = element['pin']
               sx = self.convert_vals(elem_vals['x'])
               sy = self.convert_y_vals(elem_vals['y'])
               ex = sx
               ey = sy
               num_x = sx
               num_y = sy
               name_x = sx
               name_y = sy
               if elem_vals['o'] == 0:
                   ex = sx + self.multiply_vals(elem_vals['l'])
                   ey = sy
                   name_x = ex + self.multiply_vals(elem_vals['name_offset'])
                   name_y = ey
                   num_x = sx + self.multiply_vals(elem_vals['name_offset'])
                   num_y = sy
                   if not elem_vals['hide_num']:
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       #dc.DrawText(elem_vals['number'], num_x, num_y)
                       rect = wx.Rect(num_x-10,num_y-13, 10,10) # TO DO: CHANGE VALUES BY SCALE
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       dc.DrawLabel(elem_vals['number'],rect,alignment=wx.ALIGN_CENTER|wx.ALIGN_TOP)
                   if not elem_vals['hide_name']:
                       rect = wx.Rect(name_x-5,name_y-10, 10,10)
                       dc.SetTextForeground(wx.Colour(0,100,100))
                       dc.DrawLabel(elem_vals['name'],rect,alignment=wx.ALIGN_LEFT|wx.ALIGN_TOP)
               elif elem_vals['o'] == 90:
                   ex = sx
                   ey = sy - self.multiply_vals(elem_vals['l'])
                   name_x = ex
                   name_y = ey - self.multiply_vals(elem_vals['name_offset'])
                   num_x = sx
                   num_y = sy - self.multiply_vals(elem_vals['name_offset'])
                   if not elem_vals['hide_num']:
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       dc.DrawRotatedText(elem_vals['number'], num_x-15,num_y+10,90)
                   if not elem_vals['hide_name']:
                       dc.SetTextForeground(wx.Colour(0,100,100))
                       dc.DrawRotatedText(elem_vals['name'], name_x-10,name_y+5,90)
               elif elem_vals['o'] == 180:
                   ex = sx - self.multiply_vals(elem_vals['l'])
                   ey = sy
                   name_x = ex - self.multiply_vals(elem_vals['name_offset'])
                   name_y = ey
                   num_x = sx - self.multiply_vals(elem_vals['name_offset'])
                   num_y = sy
                   if not elem_vals['hide_num']:
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       rect = wx.Rect(num_x,num_y-13, 10,10)
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       dc.DrawLabel(elem_vals['number'],rect,alignment=wx.ALIGN_CENTER|wx.ALIGN_TOP)
                   if not elem_vals['hide_name']:
                       rect = wx.Rect(name_x-5,name_y-5, 10,10)
                       dc.SetTextForeground(wx.Colour(0,100,100))
                       dc.DrawLabel(elem_vals['name'],rect,alignment=wx.ALIGN_RIGHT|wx.ALIGN_CENTER)
               elif elem_vals['o'] == 270:
                   ex = sx
                   ey = sy + self.multiply_vals(elem_vals['l'])
                   name_x = ex
                   name_y = ey + self.multiply_vals(elem_vals['name_offset'])
                   num_x = sx
                   num_y = sy + self.multiply_vals(elem_vals['name_offset'])
                   if not elem_vals['hide_num']:
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       rect = wx.Rect(num_x-5,num_y-5, 10,10)
                       dc.SetTextForeground(wx.Colour(169,0,0))
                       dc.DrawRotatedText(elem_vals['number'], num_x-15,num_y-2,90)
                   if not elem_vals['hide_name']:
                       rect = wx.Rect(name_x-5,name_y-5, 10,10)
                       dc.SetTextForeground(wx.Colour(0,100,100))
                       dc.DrawRotatedText(elem_vals['name'], name_x-10,name_y+20,90)
               dc.DrawLine(sx,sy,ex,ey)
           if list(element)[0] == 'label':
                elem_vals = element['label']
                x = self.convert_vals(elem_vals['x'])
                y = self.convert_y_vals(elem_vals['y'])
                text = elem_vals['text']
                rect = wx.Rect(x,y, 20,20)
                dc.SetTextForeground(wx.Colour(0,100,100))
                dc.DrawLabel(text,rect,alignment=wx.ALIGN_RIGHT|wx.ALIGN_CENTER)
           if list(element)[0] == 'pline':
               pts = element['pline']
               for i in range(0,len(pts)-1):
                   if i < len(pts)-1:
                       sx = self.convert_vals(pts[i][0])
                       sy = self.convert_y_vals(pts[i][1])
                       ex = self.convert_vals(pts[i+1][0])
                       ey = self.convert_y_vals(pts[i+1][1])
                       dc.DrawLine(sx,sy,ex,ey)

class FootprintPreviewPanel(wx.Panel):
    def __init__(self, parent, draw_elements):
        wx.Panel.__init__(self,parent,size=(200,115))
        self.SetOwnBackgroundColour(wx.Colour(0,0,0))
        self.InitUI()
        self.draw_list = draw_elements
        self.min_x = 0
        self.width = 0
        self.min_y = 0
        self.height = 0
        self.scale = 1

    def InitUI(self):
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        self.Show(True)

    def convert_vals(self,val):
        new_value = int((val*10))
        if self.min_x < 0:
            new_value += int(self.min_x * -10)
        if self.width > 0:
            new_value += int(((200/self.scale) - self.width) / 2)
        return new_value

    def convert_y_vals(self,val):
        new_value = int((val*10))
        if self.min_y < 0:
            new_value += int(self.min_y * -10)
        if self.height > 0:
            new_value += int(((115/self.scale) - self.height) / 2)
        return new_value

    def multiply_vals(self,val):
        return int(val*10)


    def OnPaint(self, e):
       dc = wx.PaintDC(self)
       brush = wx.Brush(wx.Colour(0,0,0))
       dc.SetUserScale(self.scale,self.scale)
       dc.SetBackground(brush)
       dc.SetTextForeground(wx.Colour(0,100,100))

       dc.Clear()
       for element in self.draw_list:
        if list(element)[0] == 'line':
            elem_vals = element['line']
            sx = self.convert_vals(elem_vals['sx'])
            sy = self.convert_y_vals(elem_vals['sy'])
            ex = self.convert_vals(elem_vals['ex'])
            ey = self.convert_y_vals(elem_vals['ey'])
            layer = elem_vals['layer']

            if layer == 'F.Fab':
                dc.SetPen(wx.Pen(wx.Colour(175,175,175), width=2))
            elif layer == 'F.CrtYd':
                dc.SetPen(wx.Pen(wx.Colour(255,38,226), width=1))
            dc.DrawLine(sx,sy,ex,ey)
        if list(element)[0] == 'circle':
            elem_vals = element['circle']
            cx = self.convert_vals(elem_vals['cx'])
            cy = self.convert_y_vals(elem_vals['cy'])
            rad = self.multiply_vals(elem_vals['r'])
            layer = elem_vals['layer']
            dc.SetBrush(wx.Brush(wx.Colour(0,0,0)))
            if layer == 'F.Fab':
                dc.SetPen(wx.Pen(wx.Colour(175,175,175), width=2))
            elif layer == 'F.CrtYd':
                dc.SetPen(wx.Pen(wx.Colour(255,38,226), width=1))
            dc.DrawCircle(cx,cy,rad)
        if list(element)[0] == 'poly':
            orig_pts = element['poly']
            draw_pts = []
            for t_pts in orig_pts:
                d_x = self.convert_vals(t_pts[0])
                d_y = self.convert_y_vals(t_pts[1])
                draw_pts.append((d_x,d_y))
            dc.SetPen(wx.Pen(wx.Colour(200,52,52), width=1))
            dc.SetBrush(wx.Brush(wx.Colour(200,52,52)))
            dc.DrawPolygon(draw_pts)
        if list(element)[0] == 'pad':
            elem_vals = element['pad']
            
            number = elem_vals['number']
            type = elem_vals['type']
            s_type = elem_vals['s_type']
            x = self.convert_vals(elem_vals['x'])
            y = self.convert_y_vals(elem_vals['y'])
            w = self.multiply_vals(elem_vals['w'])
            h = self.multiply_vals(elem_vals['h'])
            orientation = elem_vals['orientation']

            if orientation == 90 or orientation == 270:
                temp_w = w 
                w = h
                h = temp_w

            if s_type == 'thru_hole':
                dc.SetPen(wx.Pen(wx.Colour(220,177,45), width=1))
                dc.SetBrush(wx.Brush(wx.Colour(220,177,45)))
            else:
                dc.SetPen(wx.Pen(wx.Colour(200,52,52), width=1))
                dc.SetBrush(wx.Brush(wx.Colour(200,52,52)))

            if type == 'roundrect':
                radius = -1*(elem_vals['rratio'])
                dc.DrawRoundedRectangle(wx.Point(x-int(w/2),y-int(h/2)), wx.Size(w,h), radius)
                
            elif type == 'rect':
                dc.DrawRectangle(wx.Point(x-int(w/2),y-int(h/2)), wx.Size(w,h))
            
            elif type == 'oval':
                dc.DrawEllipse(wx.Point(x-int(w/2),y-int(h/2)),wx.Size(w,h))

            elif type == 'circle':
                dc.DrawEllipse(wx.Point(x-int(w/2),y-int(h/2)),wx.Size(w,h))

            elif type == 'custom':
                pts_list = []
                orig_pts = elem_vals['poly']
                max_x = -500
                min_x = 500
                max_y = -500
                min_y = 500

                for o_pt in orig_pts:
                    p_x = self.multiply_vals(o_pt[1])
                    p_y = self.multiply_vals(o_pt[2])
                    max_x = max(max_x, p_x)
                    min_x = min(min_x, p_x)
                    max_y = max(max_y, p_y)
                    min_y = min(min_y, p_y)

                    pts_list.append((p_x + x,p_y + y))

                dc.DrawPolygon(pts_list)
                pts_list = []
                

            if s_type == 'thru_hole':
                drill = elem_vals['drill']
                dc.SetPen(wx.Pen(wx.Colour(0,0,0), width=1))
                dc.SetBrush(wx.Brush(wx.Colour(0,0,0)))
                if len(drill) == 1:
                    dc.DrawCircle(x,y, multiply_vals(drill[0]/2))

            logging.warning(self.scale)
            dc.SetTextForeground(wx.Colour(249,234,234))
            font = wx.Font(pointSize = self.scale, family = wx.DEFAULT,
               style = wx.NORMAL, weight = wx.NORMAL,
               faceName = 'Consolas')
            
            dc.SetFont(font)
            if type == 'custom':
                dc.DrawLabel(number + '', wx.Rect(x + min_x, y + min_y, max_x-min_x, max_y-min_y), alignment=wx.ALIGN_CENTER)
            else:
                dc.DrawLabel(number + '', wx.Rect(wx.Point(x-int(w/2),y-int(h/2)), wx.Size(w,h)), alignment=wx.ALIGN_CENTER)

class Main_Menu(wx.Frame):
    def __init__(self, parent, title):
        '''
        creates frame elements for main ecoEDA frame / helper
        '''

        # FRAME STRUCTURE
        super(Main_Menu, self).__init__(parent, pos=(1000,200), size = (320,200), style=wx.CAPTION)
        panel = wx.Panel(self, style=wx.BORDER_THEME)
        panel.SetOwnBackgroundColour(wx.Colour(177,237,173))

        vbox = wx.BoxSizer(wx.VERTICAL)
        bm_logo = wx.Bitmap(getdirpath("assets/logo.png"), wx.BITMAP_TYPE_PNG) # to change in source build
        sbm_logo = wx.StaticBitmap(panel,bitmap=bm_logo)
        lbl = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        lbl.SetLabel("Welcome to ecoEDA")
        font_lbl_type = wx.Font(18, wx.SWISS, wx.BOLD, wx.NORMAL)
        lbl.SetFont(font_lbl_type)

        desc_text = wx.StaticText(panel,-1,style = wx.ALIGN_LEFT)
        desc_text.SetLabel("ecoEDA is running. As you add components, suggestions will pop up. Call this window with main_menu.Show() if you need to access these other non-suggestion tools.")
        desc_text.Wrap(300)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(sbm_logo,0,wx.ALIGN_CENTER_VERTICAL)
        hbox.AddSpacer(8)
        hbox.Add(lbl,0, wx.ALIGN_CENTER)

        
        #DISMISS BUTTON
        btn_x = wx.Button(panel, -1, "x", size = wx.Size(20,20), pos = wx.Point(290,6))
        btn_x.Bind(wx.EVT_BUTTON, self.OnDismiss)
        

        # OPTIONS
        # kill ecoEDA subprocesses and revisit dismissed suggestions
        btn_revisit = wx.Button(panel, -1, "revisit dismissed suggestions")
        btn_revisit.Bind(wx.EVT_BUTTON, self.OnRevisit)

        '''
        btn_close_subp = wx.Button(panel, -1, "close ecoEDA subprocesses") 
        '''

        vbox.Add(hbox)
        vbox.AddSpacer(10)
        vbox.Add(desc_text)
        vbox.AddSpacer(10)
        vbox.Add(btn_revisit)
        hbox_main = wx.BoxSizer(wx.HORIZONTAL)
        hbox_main.AddSpacer(8)
        hbox_main.Add(vbox)
        panel.SetSizer(hbox_main)
        hbox_main.Fit(panel)
        self.Layout()

    def OnDismiss(self, event):
        self.Hide()

    def OnRevisit(self, event):
        client.send_message("/revisit_dismissed", "revisit")
        self.Hide()


frame = wx.FindWindowByName("SchematicFrame")
helper = Suggestion_Helper()

exact_match_notif = Exact_Match_Notif(None, "ecoEDA suggestion")
exact_match_review = Exact_Match_Review(None, "exact match")

drop_in_notif = Drop_In_Notif(None, "ecoEDA suggestion")
drop_in_review = Drop_In_Review(None, "drop in")

diff_fp_notif = Diff_FP_Notif(None, "ecoEDA suggestion")
diff_fp_review = Diff_FP_Review(None, "different footprint")

ranked_notif = Ranked_Notif(None, "ecoEDA suggestion")
ranked_list = Ranked_List(None, "ecoEDA suggestion")
ranked_review = Ranked_Review(None, "ranked review")

subcircuit_notif = Subcircuit_Notif(None, "ecoEDA suggestion")
subcircuit_review = Subcircuit_Review(None, "ecoEDA suggestion")

main_menu = Main_Menu(None, "ecoEDA main menu")
main_menu.Show()


# server functions
def parse_added_part(unused_addr, args):
    helper.orig_part_dict = json.loads(args)

def parse_exact_match(unused_addr, args):
    if not helper.lock_suggestions:
        helper.matched_part_dict = json.loads(args)
        partname = helper.orig_part_dict["lib_id"].split(":")[1]
        exact_match_notif.set_component(partname)
        exact_match_notif.Show()
        helper.lock_suggestions = True

def parse_drop_in(unused_addr, args):
    if not helper.lock_suggestions:
        helper.matched_part_dict = json.loads(args)
        partname = helper.orig_part_dict["lib_id"].split(":")[1]
        drop_in_notif.set_component(partname)
        drop_in_notif.Show()
        helper.lock_suggestions = True

def parse_diff_fp(unused_addr, args):
    if not helper.lock_suggestions:
        helper.matched_part_dict = json.loads(args)
        partname = helper.orig_part_dict["lib_id"].split(":")[1]
        diff_fp_notif.set_component(partname)
        diff_fp_notif.Show()
        helper.lock_suggestions = True

def parse_ranked_list(unused_addr, args):
    if not helper.lock_suggestions:
        helper.suggestions_dict = json.loads(args)
        helper.unfiltered_suggestions_dict = helper.suggestions_dict
        for suggestion in helper.suggestions_dict:
            helper.sugg_components.append(suggestion)
        partname = helper.orig_part_dict["lib_id"].split(":")[1]
        ranked_notif.set_component(partname)
        ranked_notif.Show()
        helper.lock_suggestions = True

def parse_subcircuit(unused_addr, args):
    if not helper.lock_suggestions:
        helper.matched_part_dict = json.loads(args)
        partname = helper.orig_part_dict["lib_id"].split(":")[1]
        subcircuit_notif.set_component(partname)
        subcircuit_notif.Show()
        helper.lock_suggestions = True

def unlock_suggestions(unused_addr, args):
    helper.lock_suggestions = False


dispatcher = dispatcher.Dispatcher()

dispatcher.map("/orig_part", parse_added_part)

#four suggestion types
dispatcher.map("/exact_match", parse_exact_match)
dispatcher.map("/drop_in", parse_drop_in)
dispatcher.map("/diff_fp", parse_diff_fp)
dispatcher.map("/ranked_list", parse_ranked_list)
dispatcher.map("/subcircuit", parse_subcircuit)
dispatcher.map("/unlock", unlock_suggestions)

client = udp_client.SimpleUDPClient("127.0.0.1", 5006)

def server_thread(server):
      print("Serving on {}".format(server.server_address))
      server.serve_forever()

server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", 5005), dispatcher)
ser_thread = threading.Thread(target=server_thread, args=(server,))
ser_thread.daemon = True
ser_thread.start()

