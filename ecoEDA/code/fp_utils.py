import os, sys

UTIL_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), 'util'))
sys.path.append(UTIL_DIR)

from Objectifier import Objectifier,Node

from sexpdata import dumps
import sexpr
import math

def _get_array(data, value, result=None, level=0, max_level=None):
    """return the array which has value as first element"""
    if result is None: result = []

    if max_level is not None and max_level <= level:
        return result

    level += 1

    for i in data:
        if type(i) == type([]):
            _get_array(i, value, result, level=level, max_level=max_level)
        else:
            if i == value:
                result.append(data)
    return result

def convert_vals(val):
    new_value = int((val*30)) + 500
    return new_value

def convert_y_vals(val):
    new_value = int((val*30)) + 250
    return new_value

def multiply_vals(val):
    return int(val*30)


def get_fp_draw_elements(fp_dir, fp_name):
	if len(fp_name) > 1:
		fp = fp_name.split(":")
	else:
		fp = ''

	fp_path = ""

	min_x = 50
	max_x = -50
	min_y = 50
	max_y = -50

	if len(fp) > 1:
		fp_path = get_fp_path(fp_dir, fp[0],fp[1])
	elif len(fp) == 1:
		fp_path = get_fp_path_missing_lib(fp_dir, fp_name)
	else:
		return [], {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}

	if os.path.isfile(fp_path):
		f_name = open(fp_path)
		lines = ''.join(f_name.readlines())
		sexpr_data = sexpr.parse_sexp(lines)
		f_name.close()

		fp_draw_list = list()
		fp_pad_list = _get_array(sexpr_data, 'pad', max_level=2)
		fp_line_list = _get_array(sexpr_data, 'fp_line', max_level=2)
		fp_circle_list = _get_array(sexpr_data, 'fp_circle', max_level=2)
		fp_poly_list = _get_array(sexpr_data, 'fp_poly', max_level=2)

		for pad_item in fp_pad_list:
			# only look for things in F.Cu 
			layers_list = _get_array(pad_item, 'layers')[0]
			if ('F.Cu' in layers_list[1:]) or ('*.Cu' in layers_list[1:]):
				if pad_item[3] == 'roundrect':
					sx = pad_item[4][1] - (pad_item[5][1]/2.0)
					sy = pad_item[4][2] - (pad_item[5][2]/2.0)

					ex = sx + (pad_item[5][1])
					ey = sy + (pad_item[5][2])

					min_x = min(min_x, sx, ex)
					min_y = min(min_y, sy, ey)
					max_x = max(max_x, sx, ex)
					max_y = max(max_y, sy, ey)

					pad_data_obj = {'pad': {'number': pad_item[1],
											's_type': pad_item[2],
											'type': pad_item[3],
											'x': pad_item[4][1],
											'y': pad_item[4][2],
											'w': pad_item[5][1],
											'h': pad_item[5][2],
											'rratio': _get_array(pad_item, 'roundrect_rratio')[0][1]}}
				elif pad_item[3] == 'custom':
					sx = pad_item[4][1] - (pad_item[5][1]/2.0)
					sy = pad_item[4][2] - (pad_item[5][2]/2.0)

					ex = sx + (pad_item[5][1])
					ey = sy + (pad_item[5][2])

					min_x = min(min_x, sx, ex)
					min_y = min(min_y, sy, ey)
					max_x = max(max_x, sx, ex)
					max_y = max(max_y, sy, ey)
					pad_data_obj  = {'pad': {'number': pad_item[1],
											's_type': pad_item[2],
											'type': pad_item[3],
											'x': pad_item[4][1],
											'y': pad_item[4][2],
											'w': pad_item[5][1],
											'h': pad_item[5][2],
											'poly': _get_array(pad_item, 'gr_poly')[0][1][1:]}}
				else:
					pad_data_obj = {'pad': {'number': pad_item[1],
											's_type': pad_item[2],
											'type': pad_item[3],
											'x': pad_item[4][1],
											'y': pad_item[4][2],
											'w': pad_item[5][1],
											'h': pad_item[5][2]}}
					sx = pad_item[4][1] - (pad_item[5][1]/2.0)
					sy = pad_item[4][2] - (pad_item[5][2]/2.0)

					ex = sx + (pad_item[5][1])
					ey = sy + (pad_item[5][2])

					min_x = min(min_x, sx, ex)
					min_y = min(min_y, sy, ey)
					max_x = max(max_x, sx, ex)
					max_y = max(max_y, sy, ey)
				if pad_item[2] == 'thru_hole':
					pad_data_obj['pad']['drill']= _get_array(pad_item, 'drill')[0][1:]

				if len(pad_item[4]) == 4:
					pad_data_obj['pad']['orientation'] = pad_item[4][3]
				else:
					pad_data_obj['pad']['orientation'] = 0
				fp_draw_list.append(pad_data_obj)

		for line_item in fp_line_list:
			sx = line_item[1][1]
			sy = line_item[1][2]
			ex = line_item[2][1]
			ey = line_item[2][2]

			min_x = min(min_x, sx, ex)
			min_y = min(min_y, sy, ey)
			max_x = max(max_x, sx, ex)
			max_y = max(max_y, sy, ey)

			line_data_obj = {'line': {'sx': line_item[1][1],
										'sy': line_item[1][2],
										'ex': line_item[2][1],
										'ey': line_item[2][2],
										'layer': line_item[3][1]}}
			fp_draw_list.append(line_data_obj)

		for circle_item in fp_circle_list:
			cx = circle_item[1][1]
			cy = circle_item[1][2]
			ex = circle_item[2][1]
			ey = circle_item[2][2]
			radius = math.dist([cx,cy],[ex,ey])

			min_x = min(min_x, cx-radius)
			min_y = min(min_y, cy - radius)
			max_x = max(max_x, cx + radius)
			max_y = max(max_y, cy + radius)

			circle_data_obj = {'circle': {'cx': cx,
										'cy': cy,
										'r': radius,
										'layer': circle_item[3][1]}}
			fp_draw_list.append(circle_data_obj)

		for poly_item in fp_poly_list:
			pts = []
			for point in poly_item[1][1:]:
				pts.append(point[1:])
				min_x = min(min_x, point[1])
				min_y = min(min_y, point[2])
				max_x = max(max_x, point[1])
				max_y = max(max_y, point[2])
			poly_data_obj = {'poly': pts}
			fp_draw_list.append(poly_data_obj)

	fp_draw_list.sort(key=get_order)
	bounds = {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}
	return fp_draw_list, bounds

def get_fp_path_missing_lib(fp_dir, fp_name):
	for item in os.listdir(fp_dir):
		item_path = os.path.join(fp_dir, item)
		if item == (fp_name + ".kicad_mod"):
			return item_path
		elif os.path.isdir(item_path):
			for d_item in os.listdir(item_path):
				d_item_path = os.path.join(item_path, d_item)
				if d_item == fp_name + ".kicad_mod":
					return d_item_path
	return None

def get_fp_path(fp_dir, fp_lib, fp_name):
	return fp_dir + fp_lib + ".pretty/" + fp_name + ".kicad_mod"
	    

def get_order(element):
    if list(element)[0] == 'line':
        return 2
    elif list(element)[0] == 'circle':
        return 1
    elif list(element)[0] == 'pad':
    	return 3
    else:
        return 2
