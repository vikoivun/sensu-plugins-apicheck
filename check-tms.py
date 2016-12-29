#!/usr/bin/env python
#
#   check-tms
#
# DESCRIPTION:
#   Plugin to test the old, but still used, TMS map tile API for basic
#   functionality. Loads several tiles around the given centerpoint
#   and verifies that they loaded OK.
#
# OUTPUT:
#   plain text describing the abnormal condition encountered
#
# PLATFORMS:
#   Only tested on Linux
#
# DEPENDENCIES:
#   pip: sensu_plugin
#
# USAGE:
#   Start with --help to see applicable parameters
# NOTES:
#   Everything is suspect
#
# LICENSE:
#   Ville Koivunen  ville.koivunen@hel.fi
#   Released under the same terms as Sensu (the MIT license); see LICENSE
#   for details.
import requests
from lxml import etree
from sensu_plugin import SensuPluginCheck

class TileMapService(object):
    def __init__(self, root_url):
        root = root_url
        
        resp = requests.get(root_url)
        root = etree.fromstring(resp.content)
        maplist = root.xpath('/TileMapService/TileMaps')[0].getchildren()
        
        self.maps = [dict(x.items()) for x in maplist]

        for map in self.maps:
            resp = requests.get(map['href'])
            root = etree.fromstring(resp.content)
            # Flatten the thing
            map['bbox'] = [dict(x.items()) for x in root.xpath('/TileMap/BoundingBox')][0]
            map['origin'] = [dict(x.items()) for x in root.xpath('/TileMap/Origin')][0]
            map['tileformat'] = [dict(x.items()) for x in root.xpath('/TileMap/TileFormat')][0]
            map['tilesets'] = [dict(x.items()) for x in root.xpath('/TileMap/TileSets')[0].getchildren()]

    def get_maplist(self):
        return [map['title'] for map in self.maps]

    def get_tilexy_from_coords(self, map_title, order, x, y, forced_origin=None):
        map = [map for map in self.maps if map['title'] == map_title][0]

        bbox = map['bbox']
        if forced_origin is None:
            origin = map['origin']
        else:
            origin = {'x': forced_origin[0], 'y': forced_origin[1]}
        heigth, width = int(map['tileformat']['height']), int(map['tileformat']['width'])
        ratios_for_orders = {int(ts['order']): float(ts['units-per-pixel']) for ts in map['tilesets']}

        tx = int((x - float(origin['x'])) / ratios_for_orders[order] / width)
        ty = int((y - float(origin['y'])) / ratios_for_orders[order] / heigth)

        return (tx,ty)

    def get_tile(self, map_title, order, x, y):
        map = [map for map in self.maps if map['title'] == map_title][0]
                
        tileset = [tileset for tileset in map['tilesets'] if tileset['order'] == str(order)][0]
        tileset_url = tileset['href']
        tile_url = tileset_url + "/" + str(x) + "/" + str(y) + "." + map['tileformat']['extension']
        resp = requests.get(tile_url)
        tile = {'data': resp.content,
                'url': tile_url,
                'content_type': resp.headers['content-type'],
                'status_code': resp.status_code,
                }
        
        return tile
        
class TMSCheck(SensuPluginCheck):
    def setup(self):
        # self.parser comes from SensuPluginCheck
        self.parser.add_argument('-r', '--root', required=True, type=str,
                                help='TMS root to use for findings maps')
        self.parser.add_argument('-l', '--list-maps', required=False, action='store_true',
                                help='List maps available at root')        
        self.parser.add_argument('-t', '--service', required=False, type=str,
                                help='Service type to check (currently only tms is supported)')
        self.parser.add_argument('-p', '--point', required=False, type=float,
                                nargs=2, help="Center point (x,y) for tests in native coordinates for the map")
        self.parser.add_argument('-z', '--zoom', required=False, type=int,
                                help="Center zoom level for tests")
        self.parser.add_argument('-s', '--side-length', required=False, type=int, default=1,
                                help="Side length in tiles for the box to load around the center point")
        self.parser.add_argument('-o', '--origo', required=False, type=float, default=None,
                                nargs=2, help="Force origo to this point (for misconfigured servers)")
        self.parser.add_argument('-m', '--map', required=False, type=str,
                                help="Map to run the checks against")
        self.parser.add_argument('-k', '--keep-files', required=False, action='store_true',
                                help="Keep the downloaded files (for debugging)")
        self.parser.add_argument('--verbose', '-v', action='count')

    def point_to_box(self, x, y, side_length):
        offset = int(side_length / 2)
        odd = side_length % 2
    
        x_range = range(x-offset, x+offset+odd)
        y_range = range(y-offset, y+offset+odd)
        
        return [(x,y) for x in x_range for y in y_range]

    def run(self):
        self.check_name('OWS test')

        tms = TileMapService(self.options.root)

        map = self.options.map
        x, y = self.options.point
        zoom = self.options.zoom
        origo = self.options.origo

        if self.options.list_maps:
            print("Available Maps:")
            for map in tms.get_maplist():
                print(map)

        centerx, centery = tms.get_tilexy_from_coords(map, zoom, x, y, origo)

        tiles = self.point_to_box(centerx, centery, self.options.side_length)

        for tile in tiles:
            image = tms.get_tile(map, zoom, tile[0], tile[1])
            if self.options.keep_files:
                with open('tile{}{}.jpg'.format(tile[0],tile[1]), 'wb') as file:
                    file.write(image['data'])
            if self.options.verbose:
                print(image['url'])
            if image['status_code'] != 200:
                self.critical('Tile at URL: {} failed to load. Status code {}'.format(image['url'], image['status_code']))
            
        self.ok('Tiles within test area loaded successfully')

if __name__ == "__main__":
    f = TMSCheck()
