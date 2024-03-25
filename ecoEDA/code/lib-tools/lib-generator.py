#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Script to generate ecoEDA symbol library based on csv (see HOWTO.md for details).

# Modified from Kicad Library Utilities
import os, sys

UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'util'))
sys.path.append(UTIL_DIR)

from kicad_sym import *
from kicad_mod import *
import csv
import argparse

def create_ecoEDA_library(csv_file, symbols_path):

    reader = csv.DictReader(open(csv_file))


    from pathlib import Path

    valid_symbol = False
    symbol_dict = dict()

    not_found = False

    if Path("../ecoEDA.kicad_sym").is_file():
        lib = KicadLibrary.from_file('../ecoEDA.kicad_sym')
    else:
        lib = KicadLibrary('ecoEDA.kicad_sym')

    #populate symbol_dict based on original ecoEDA.kicad_sym library to not overwrite preexisting symbols
    for symbol in lib.symbols:
        n_name = symbol.name
        if n_name in symbol_dict.keys():
            i = symbol_dict[n_name]['count']
            orig_name = n_name
            n_name = n_name + "_" + str(i)
            symbol_dict[orig_name]['count'] = i + 1
        else:
            symbol_dict[n_name] = dict()
            symbol_dict[n_name]['count'] = 0

    #parse through each row of new file
    for row in reader:
        sym_key = row.pop('Symbol-KICAD-URL')
        symbollib = sym_key.split(":")[0]
        symb = sym_key.split(":")[1]
        libcad = ".kicad_sym"
        symlib = symbollib + libcad

        # handles for custom symbols
        if 'Custom_symbol' in row.keys():
            flag = row.pop('Custom_symbol')
        else:
            flag = 'No'

        if flag == 'Yes':
            orig_sym_lib = KicadLibrary.from_file("Custom_Symbols/" + symlib)
        else:
            orig_sym_lib = KicadLibrary.from_file(symbols_path + symlib)

        #get symbol info for symbol to base off of from default libraries
        for symbol in orig_sym_lib.symbols:
            if symb == symbol.name:
                #check for the case when the symbol extends another
                if symbol.extends != None:
                    for ex_symb in orig_sym_lib.symbols:
                        if ex_symb.name == symbol.extends:
                            new_symbol = ex_symb
                else:
                    new_symbol = symbol
                    not_found = True
                valid_symbol = True
            


            if valid_symbol == True:
                green = Color(0,255,0,1) # doesn't do anything
                small = new_symbol.is_small_component_heuristics()


                # use small ecoEDA symbol if it is a really small component
                if small == False:
                    new_symbol.circles.append(Circle(0,-1,2, stroke_width=0.15, stroke_color=green, fill_color=green))
                    new_symbol.arcs.append(Arc(-0.6,-1.9,0.8,0,0,0, stroke_width=0.2, stroke_color=green))
                    new_symbol.arcs.append(Arc(-0.6,-1.82,0.8,0,0,-1.65, stroke_width=0.2, stroke_color=green))
                    new_symbol.arcs.append(Arc(-0.8,-2.2,0.8,0,0,-0.7, stroke_width=0.2, stroke_color=green))
                else:
                    polylines =  new_symbol.polylines
                    if len(polylines) == 0:
                        new_symbol.circles.append(Circle(0.02,0.13,0.8, stroke_width=0.15, stroke_color=green, fill_color=green))
                        new_symbol.arcs.append(Arc(-0.2,-0.4,0.5,0.8,-0.2,0.35, stroke_width=0.2, stroke_color=green))
                        new_symbol.arcs.append(Arc(-0.2,-0.4,0.5,0.8,0,1.2, stroke_width=0.2, stroke_color=green))
                        new_symbol.arcs.append(Arc(-0.3,-0.5,0.5,0.8,0.4,0.6, stroke_width=0.2, stroke_color=green))
                    else:
                        for poly in polylines:
                            center = poly.get_center_of_boundingbox()
                            bounding = poly.get_boundingbox()
                        if center[0] == 0 and center[1] != 0 or center[0] != 0 and center[1] == 0:
                            center_x = center[0]
                            center_y = center[1]
                        else:
                            center_x = bounding[0]
                            center_y = bounding[1]

                        #base off of bounds
                        startx_l_arc = center_x + 2.6
                        starty_l_arc = center_y + 2
                        endx_l_arc = startx_l_arc + 0.7
                        endy_l_arc = starty_l_arc + 0.9
                        l_mid_y = endy_l_arc
                        l_mid_x = center_x + 2.8
                        r_mid_x = center_x + 2
                        r_mid_y = l_mid_y
                        mid_arc_start = starty_l_arc - 0.35


                        new_symbol.circles.append(Circle(center_x+2.85,center_y + 2.4,0.85, stroke_width=0.1, stroke_color=green, fill_color=green))
                        new_symbol.arcs.append(Arc(startx_l_arc, starty_l_arc,endx_l_arc,endy_l_arc,l_mid_x,l_mid_y, stroke_width=0.2, stroke_color=green))
                        new_symbol.arcs.append(Arc(startx_l_arc, starty_l_arc,endx_l_arc,endy_l_arc,r_mid_x,r_mid_y, stroke_width=0.2, stroke_color=green))
                        new_symbol.arcs.append(Arc(startx_l_arc,mid_arc_start,endx_l_arc,endy_l_arc,center_x+3.5,center_y + 3, stroke_width=0.2, stroke_color=green))
                
                n_name = row.pop('Component Name')
                if n_name in symbol_dict.keys():
                    i = symbol_dict[n_name]['count']
                    orig_name = n_name
                    n_name = n_name + "_" + str(i)
                    symbol_dict[orig_name]['count'] = i + 1
                else:
                    symbol_dict[n_name] = dict()
                    symbol_dict[n_name]['count'] = 0
                new_symbol.name = n_name
                new_symbol.libname = "ecoEDA"
                valid_symbol = False
            
                n_val = row.pop('Value')
                val = new_symbol.get_property('Value')
                val.value = n_val

                fp_val = row.pop('Footprint-KICAD-URL')
                n_fp = fp_val
                fp = new_symbol.get_property('Footprint')
                fp.value = n_fp

                n_ds = row.pop('Datasheet')
                ds = new_symbol.get_property('Datasheet')
                ds.value = n_ds

                n_desc = row.pop('Description')
                desc = new_symbol.get_property('ki_description')
                if desc == None:
                    desc = Property('ki_description', n_desc, len(new_symbol.properties) + 1)
                    desc.effects.is_hidden = True
                    new_symbol.properties.append(desc)
                else:
                    desc.value = n_desc

                # desc.value = n_desc

                n_kw = row.pop('Keywords')
                kw = new_symbol.get_property('ki_keywords')
                if kw == None:
                    kw = Property('ki_keywords', n_kw, len(new_symbol.properties) + 1)
                    kw.effects.is_hidden = True
                    new_symbol.properties.append(kw)
                else:
                    kw.value = n_kw

                
                n_src = row.pop('Source')
                prop_src = Property('Source', n_src, len(new_symbol.properties) + 1)
                prop_src.effects.is_hidden = True
                new_symbol.properties.append(prop_src)

                prop_ecoEDA = Property('ecoEDA', 'Yes', len(new_symbol.properties) + 1)
                prop_ecoEDA.effects.is_hidden = True
                new_symbol.properties.append(prop_ecoEDA)

                n_species = row.pop('Species')
                prop_species= Property('Species', n_species,len(new_symbol.properties) + 1)
                prop_species.effects.is_hidden = True
                new_symbol.properties.append(prop_species)

                n_genus = row.pop('Genus')
                prop_genus= Property('Genus', n_genus,len(new_symbol.properties) + 1)
                prop_genus.effects.is_hidden = True
                new_symbol.properties.append(prop_genus)

                if 'Exact match' in row.keys():
                    n_sym_match = row.pop('Exact match')
                    n_sym_match = n_sym_match + ", " + symb
                else:
                    n_sym_match = symb

                prop_sym_match= Property('Exact match', n_sym_match,14)
                prop_sym_match.effects.is_hidden = True
                new_symbol.properties.append(prop_sym_match)

                n_smd_v_tht = row.pop('SMD vs. THT')
                if n_smd_v_tht == 'smd':
                    n_smd_v_tht == 'SMD'
                if n_smd_v_tht == 'tht':
                    n_smd_v_tht = 'THT'

                prop_smd_v_tht= Property('SMD vs. THT',  n_smd_v_tht, len(new_symbol.properties) + 1)
                prop_smd_v_tht.effects.is_hidden = True
                new_symbol.properties.append(prop_smd_v_tht)

                n_teardown = row.pop('Teardown Link')
                prop_teardown = Property('Teardown Link',  n_teardown, len(new_symbol.properties) + 1)
                prop_teardown.effects.is_hidden = True
                new_symbol.properties.append(prop_teardown)

                n_qty = row.pop('Quantity')
                prop_qty = Property('Quantity',   n_qty, len(new_symbol.properties) + 1)
                prop_qty.effects.is_hidden = True
                new_symbol.properties.append(prop_qty)


                n_pcb_desig = row.pop('PCB Designator')
                prop_pbc_desig = Property('PCB Designator', n_pcb_desig, len(new_symbol.properties) + 1)
                prop_pbc_desig.effects.is_hidden = True
                new_symbol.properties.append( prop_pbc_desig)

                # TO DO - drop in script to look up same footprints?
                if 'Drop-in replacement' in row.keys():
                    n_dropin = row.pop('Drop-in replacement')
                else:
                    # if footprint specified is the same as the original symbol
                    # TO DO also add subcircuits
                    new_fp = new_symbol.get_property('Footprint').value
                    orig_sym_fp = symbol.get_property('Footprint').value

                    if new_fp != '' and new_fp == orig_sym_fp:
                        n_dropin = symbol.name
                        for d_symbol in orig_sym_lib.symbols:
                            if d_symbol.name != symbol.name:
                                d_sym_fp = d_symbol.get_property('Footprint').value
                                if d_sym_fp == orig_sym_fp:
                                    n_dropin = n_dropin + ", " + d_symbol.name
                    else:
                        n_dropin = ''

                prop_dropin = Property('Drop-in replacement',  n_dropin, len(new_symbol.properties) + 1)
                prop_dropin.effects.is_hidden = True
                new_symbol.properties.append(prop_dropin)

                #append generated symbol into library
                lib.symbols.append(new_symbol)
    #do final write of library
    lib.write()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="",
      help="The csv file with component parts to add to your ecoEDA.kicad_sym file")
    parser.add_argument("--symbol_path", default="",
      help="The directory for symbol libraries (often within KiCad/SharedSupport)")
    args = parser.parse_args()

    if (args.file != "") & (args.symbol_path != ""):
        file = args.file
        symbol_path = args.symbol_path
        create_ecoEDA_library(file, symbol_path)
    else:
        print("Please specify a csv file or symbol path.")
