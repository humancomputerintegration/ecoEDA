import argparse
import os, sys
sys.path.insert(1, '../')
from sexpdata import dumps
from Objectifier import Objectifier

import sexpr

from kicad_sym import *

# removing extra symbols that do not correspond to a recyclable electronic component
def is_true_cmpnt(footprint, lib_id):
    if lib_id.startswith("power:"):
        return False
    elif footprint.startswith("Connector_PinHeader_"):
        return False
    elif footprint.startswith("TestPoint:"):
        return False
    elif footprint.startswith("Jumper:"):
        return False
    elif lib_id.startswith("Connector_Generic:"):
        return False
    else:
        return True

# parse through the symbol libraries in the schematic
def get_sch_lib_sym_dict(file):
    sch = Objectifier(file)
    root = sch.root

    #get source (project name)

    if len(root.xpath('/kicad_sch/title_block/title')) > 0:
        prj_name = root.xpath('/kicad_sch/title_block/title')[0].childs[0]
    else:
        prj_name = file.split("/")[-1].split(".kicad_sch")[0]

    lib_sym_data = {}

    #go through each symbol, increase quantity of lib sym with each instance, collect sch references
    sym_arr = root.xpath('/kicad_sch/symbol')

    for sym in sym_arr:
        lib_id = sym.first_child.childs[0]
        uuid = dumps(sym.xpath('/symbol/uuid')[0].first_child)

        reference = ''
        footprint = ''
        value = ''
        unit = ''

        for path in root.xpath('/kicad_sch/symbol_instances/path'):
            if path.first_child[1:] == uuid:
                reference = path.childs[1].first_child
                unit = path.childs[2].first_child
                value = path.childs[3].first_child
                footprint = path.childs[4].first_child
        # create symbol data object for all values
        sym_obj = {'reference': reference, 'footprint': footprint, 'value': value, 'unit': unit}

        # do not add if is part of "not true" components libraries
        if is_true_cmpnt(footprint, lib_id):
            if lib_id in lib_sym_data.keys():
                lib_sym_data[lib_id].append(sym_obj)
            else:
                lib_sym_data[lib_id] = [sym_obj]

    return lib_sym_data, prj_name

# Identity the index of the last component with the same name (to append correct value)
def get_last_index_in_lib(name):
    lib = Objectifier("../ecoEDA.kicad_sym")
    root = lib.root

    sym_arr = root.xpath('/kicad_symbol_lib/symbol')

    last_index = None
    for sym in sym_arr:
        if sym.first_child.startswith(name):
            if "_" in sym.first_child:
                if sym.first_child.split("_")[-1].isnumeric():
                    index = int(sym.first_child.split("_")[-1])
                else:
                    index = -1
            else:
                index = -1
            if last_index is not None:
                last_index = max(last_index, index)
            else:
                last_index = index

    return last_index

# retrieve the symbol information from the file
def get_sym_prop(lib_name, file):
    f_name = open(file)
    lines = '\n'.join(f_name.readlines())
    sexpr_data = sexpr.parse_sexp(lines)

    for element in sexpr_data:
        if type(element) == type([]):
            if (element[0] == 'lib_symbols'):
                for symbol in element:
                    if symbol[1] == lib_name:
                        return symbol
    return None

# identify each unique instance of the symbol
def get_unique_instances(arr_instances):

    mod_arr_instances = []

    for instance in arr_instances:
        exists_in_m_arr = False
        for m_instance in mod_arr_instances:
            if instance['value']== m_instance['value'] and instance['footprint'] == m_instance['footprint']:
                    exists_in_m_arr = True

        if exists_in_m_arr:
            #up quantity, add pcb references
            for m_instance in mod_arr_instances:
                if instance['value']== m_instance['value'] and instance['footprint'] == m_instance['footprint']:
                    if not ((instance['unit'] != m_instance['unit']) and (instance['reference'] in m_instance['references'])):
                        m_instance['quantity'] += 1
                        m_instance['references'].append(instance['reference'])
        else:
            mod_arr_instances.append({'references': [instance['reference']],
                                      'value': instance['value'],
                                      'footprint': instance['footprint'],
                                      'unit': instance['unit'], 'quantity': 1})

    return mod_arr_instances

# generate information to add to library
def gen_lib_info(lib_sym_dict, file, prj_name):

    lib_arr = []
    for lib_sym in lib_sym_dict:
        arr_instances = lib_sym_dict[lib_sym]

        #check for naming
        if ":" in lib_sym:
            part_name = lib_sym.split(":")[1]
        else:
            part_name = lib_sym

        sym_prop_arr = []

        sym_prop = get_sym_prop(lib_sym, file)

        last_index = get_last_index_in_lib(part_name)

        if len(arr_instances) > 1:
            mod_arr_instances = get_unique_instances(arr_instances)

            for m_instance in mod_arr_instances:
                if last_index is not None:
                    lib_sym_name = part_name + "_" + str(last_index + 1)
                    last_index += 1
                else:
                    lib_sym_name = part_name
                    last_index = -1
                quantity = m_instance['quantity']
                pcb_designator = ' '.join(m_instance['references'])
                value = m_instance['value']
                footprint = m_instance['footprint']

                sym_prop = get_sym_prop(lib_sym, file)
                kicad_symbol = gen_kicad_symbol(sym_prop, lib_sym_name, quantity, prj_name, pcb_designator, value, footprint)
                lib_arr.append(kicad_symbol)
        else:
            if last_index is not None:
                lib_sym_name = part_name + "_" + str(last_index + 1)
            else:
                lib_sym_name = part_name
            quantity = 1
            pcb_designator = arr_instances[0]['reference']
            value = arr_instances[0]['value']
            footprint = arr_instances[0]['footprint']

            sym_prop = get_sym_prop(lib_sym, file)
            kicad_symbol = gen_kicad_symbol(sym_prop, lib_sym_name, quantity, prj_name, pcb_designator, value, footprint)
            lib_arr.append(kicad_symbol)

    return lib_arr

# write imported symbols to ecoEDA library
def write_symbols_to_lib(sym_arr):
    lib = KicadLibrary.from_file('../ecoEDA.kicad_sym')
    for sym in sym_arr:
        lib.symbols.append(sym)
    lib.write()

# generate the new kicad symbol (with ecoEDA symbol)
def gen_kicad_symbol(symbol_data, lib_sym_name, quantity, src, pcb_designator, value, footprint):
    name = lib_sym_name
    n_symbol = KicadSymbol(name, 'ecoEDA', 'ecoEDA.kicad_sym')
    n_symbol.add_default_properties()

    # get property fields of old symbol_data and symbol data
    unit_num = 1
    for prop in symbol_data:
        if type(prop) == type([]):
            if prop[0] == 'property':
                if prop[1] in ['ki_locked', 'ki_keywords', 'ki_description', 'ki_fp_filters', 'Datasheet', 'Reference']:
                    n_symbol.get_property(prop[1]).value = prop[2]
                elif prop[1] not in ['Value', 'Footprint']:
                    n_prop = Property(prop[1], prop[2], len(n_symbol.properties))
                    n_prop.effects.is_hidden = True
                    n_symbol.properties.append(n_prop)
            if prop[0] == 'symbol':
                has_Pins = False
                for part in prop[2:]:
                    if part[0] == 'polyline':
                        n_polyline = Polyline.from_sexpr(part, unit_num, 0)
                        n_symbol.polylines.append(n_polyline)
                    elif part[0] == 'pin':
                        n_pin = Pin.from_sexpr(part, unit_num, 0)
                        n_symbol.pins.append(n_pin)
                        has_Pins = True
                    elif part[0] == 'circle':
                        n_circle = Circle.from_sexpr(part, unit_num, 0)
                        n_symbol.circles.append(n_circle)
                    elif part[0] == 'arc':
                        n_arc = Arc.from_sexpr(part, unit_num, 0)
                        n_symbol.arcs.append(n_arc)
                    elif part[0] == 'text':
                        n_text = Text.from_sexpr(part, unit_num, 0)
                        n_symbol.texts.append(n_text)
                    elif part[0] == 'rectangle':
                        n_rectangle = Rectangle.from_sexpr(part, unit_num, 0)
                        n_symbol.rectangles.append(n_rectangle)
                    else:
                        print(prop[0] + "was not added")
                if has_Pins:
                    unit_num +=1
    n_symbol.unit_count = unit_num + 1
    # update value and footprint properties
    n_symbol.get_property('Value').value = value
    n_symbol.get_property('Footprint').value = footprint

    # add ecoEDA properties
    prop_quantity = Property('Quantity', str(quantity), len(n_symbol.properties))
    prop_quantity.effects.is_hidden = True
    n_symbol.properties.append(prop_quantity)

    prop_pcb = Property('PCB Designator', pcb_designator, len(n_symbol.properties))
    prop_pcb.effects.is_hidden = True
    n_symbol.properties.append(prop_pcb)

    prop_src = Property('Source', src, len(n_symbol.properties))
    prop_src.effects.is_hidden = True
    n_symbol.properties.append(prop_src)

    prop_ecoEDA = Property('ecoEDA', 'Yes',len(n_symbol.properties))
    prop_ecoEDA.effects.is_hidden = True
    n_symbol.properties.append(prop_ecoEDA)


    # add empty fields for other ecoEDA properties
    for prop in ['Manufacturer', 'Species', 'Genus', 'SMD vs. THT', 'Teardown Link', 'Drop-in replacement']:
        n_prop = Property(prop, '~', len(n_symbol.properties))
        n_prop.effects.is_hidden = True
        n_symbol.properties.append(n_prop)


    # add ecoEDA leaf symbol
    green = Color(0,255,0,1)
    small = n_symbol.is_small_component_heuristics()
    if small == False:
        n_symbol.circles.append(Circle(0,-1,2, stroke_width=0.15, stroke_color=green, fill_color=green))
        n_symbol.arcs.append(Arc(-0.6,-1.9,0.8,0,0,0, stroke_width=0.2, stroke_color=green))
        n_symbol.arcs.append(Arc(-0.6,-1.82,0.8,0,0,-1.65, stroke_width=0.2, stroke_color=green))
        n_symbol.arcs.append(Arc(-0.8,-2.2,0.8,0,0,-0.7, stroke_width=0.2, stroke_color=green))
    else:
        polylines =  n_symbol.polylines
        if len(polylines) == 0:
            n_symbol.circles.append(Circle(0.02,0.13,0.8, stroke_width=0.15, stroke_color=green, fill_color=green))
            n_symbol.arcs.append(Arc(-0.2,-0.4,0.5,0.8,-0.2,0.35, stroke_width=0.2, stroke_color=green))
            n_symbol.arcs.append(Arc(-0.2,-0.4,0.5,0.8,0,1.2, stroke_width=0.2, stroke_color=green))
            n_symbol.arcs.append(Arc(-0.3,-0.5,0.5,0.8,0.4,0.6, stroke_width=0.2, stroke_color=green))
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

            startx_l_arc = center_x + 2.6
            starty_l_arc = center_y + 2
            endx_l_arc = startx_l_arc + 0.7
            endy_l_arc = starty_l_arc + 0.9
            l_mid_y = endy_l_arc
            l_mid_x = center_x + 2.8
            r_mid_x = center_x + 2
            r_mid_y = l_mid_y
            mid_arc_start = starty_l_arc - 0.35


            n_symbol.circles.append(Circle(center_x+2.85,center_y + 2.4,0.85, stroke_width=0.1, stroke_color=green, fill_color=green))
            n_symbol.arcs.append(Arc(startx_l_arc, starty_l_arc,endx_l_arc,endy_l_arc,l_mid_x,l_mid_y, stroke_width=0.2, stroke_color=green))
            n_symbol.arcs.append(Arc(startx_l_arc, starty_l_arc,endx_l_arc,endy_l_arc,r_mid_x,r_mid_y, stroke_width=0.2, stroke_color=green))
            n_symbol.arcs.append(Arc(startx_l_arc,mid_arc_start,endx_l_arc,endy_l_arc,center_x+3.5,center_y + 3, stroke_width=0.2, stroke_color=green))


    return n_symbol

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="",
      help="The kicad schematic file to add to ecoEDA lib")
    args = parser.parse_args()

    if(args.file != ""):
        file = args.file
        lib_sym_dict, prj_name = get_sch_lib_sym_dict(file)
        lib_arr = gen_lib_info(lib_sym_dict, file, prj_name)
        write_symbols_to_lib(lib_arr)
    else:
      print("Please specify a file to import.")

    

