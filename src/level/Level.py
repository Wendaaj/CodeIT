import configparser
import importlib.util
import random
from pdb import set_trace
from warnings import warn

import numpy as np
import pygame

from PIL import Image
import os

from behaviours.Collide import Collide
from src.utils.CodeItWarning import CodeItWarning
from tiles.base.Tile import Tile

level_paths = {}
level_configs = {}
level_backgrounds = {}
entity_map = {}

image_file_formats = [".png", ".jpg", ".jpeg", ".bmp"]


def constructor_factory(constructor, name):
    return lambda x, y: constructor(x, y, name)


def load_entity_map():
    for path in [f.path for f in os.scandir("../entities") if f.is_dir()]:
        path = [x for x in os.scandir(path) if os.path.splitext(x)[1] == ".py"][0]
        class_name = os.path.splitext(os.path.basename(path))[0]
        if ' ' in class_name:
            raise ValueError("Entities cannot have spaces in their names, '" + class_name + "'")
        spec = importlib.util.spec_from_file_location("dynamic_load.entities." + class_name, path)
        foo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(foo)
        class_constructor = getattr(foo, class_name)
        entity_map[class_name] = constructor_factory(class_constructor, class_name)

    for path in [f.path for f in os.scandir("../tiles") if f.is_dir()]:
        paths = [x for x in os.scandir(path) if os.path.splitext(x)[1] in image_file_formats]
        if len(paths) <= 0:
            continue
        path = paths[0]
        class_name = os.path.splitext(os.path.basename(path))[0]
        if ' ' in class_name:
            raise ValueError("Tiles cannot have spaces in their names, '" + class_name + "'")
        entity_map[class_name] = constructor_factory(Tile, class_name)


load_entity_map()


def load_levels():
    for path in [f.path for f in os.scandir("../levels") if f.is_dir()]:
        config = configparser.ConfigParser()
        config.read(path + "/config.ini")
        level_name = config["General"]["Name"]
        level_paths[level_name] = path
        level_configs[level_name] = config
        paths = [x for x in os.scandir(path) if "background" in os.path.splitext(x)[0]]
        if len(paths) <= 0:
            continue
        path = paths[0]
        level_backgrounds[level_name] = pygame.image.load(os.path.relpath(path, os.getcwd()))


def get_level_by_index(index):
    level_list = []
    for level_name in level_configs.keys():
        level_index = int(level_configs[level_name]["General"]["Index"])
        if level_index == index:
            level_list.append(level_name)

    if len(level_list) <= 0:
        return
    if len(level_list) == 1:
        return Level(level_list[0])

    return Level(random.choice(level_list))


load_levels()


def hex_to_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb: tuple) -> str:
    return ('%02x%02x%02x' % rgb).upper()


def load_config(path):
    config = configparser.ConfigParser()
    config.read(path)
    return config


default_color_map = load_config("../levels/default/color-map.ini")


# returns a dictionary that maps rgb tuples to entity constructors
# @param entity_map: a dictionary that maps entity names to entity constructors.
def get_color_map(level):
    color_map = {}
    config = combine_configs(load_config(level.path + "/color-map.ini"), default_color_map)
    for key in config["Colors"]:
        color_map[hex_to_rgb(key)] = (config["Colors"][key], entity_map[config["Colors"][key]])
    return color_map


def combine_configs(c1, c2):
    combined = {}
    for category in list(set().union(c1.keys(), c2.keys())):
        combined[category] = {**(c2[category] if category in c2 else {}), **(c1[category] if category in c1 else {})}
    return combined


def load_map_image(level):
    arr3d = np.array(Image.open(level.path + "/map.bmp"))
    return arr3d, arr3d.shape[:2]


def load_entities(color_map, map_image, image_shape):
    entities = []
    entity_lookup = {}
    tiles = []

    for ix, iy in np.ndindex(image_shape):
        rgb = tuple(map_image[ix, iy])
        if rgb in color_map:
            entity = color_map[rgb][1](iy, ix)
            entity_name = color_map[rgb][0]
            if isinstance(entity, Tile):
                tiles.append(entity)
            else:
                entity.remain_on_reset = True
                if entity_name in entity_lookup:
                    entity_lookup[entity_name].append(entity)
                else:
                    entity_lookup[entity_name] = [entity]
                entities.append(entity)
        else:
            warn("CodeIT:: No Tile or entity mapped to " + rgb_to_hex(rgb), category=CodeItWarning, stacklevel=0)

    return entities, tiles, entity_lookup


class Level:
    def __init__(self, name):
        if name == "Default":
            raise ValueError("Do not instantiate the default level")
        self.path = level_paths[name]
        self.config = combine_configs(level_configs[name], level_configs["Default"])
        self.name = name
        self.entities = list()
        self.tiles = list()
        self.color_map = {}
        self.map_image = None
        self.map_shape = (0, 0)
        self.background = None
        self.entity_lookup_map = {}
        self.graveyard = []

    def load(self):
        try:
            if self.config["General"]["type"] == "Pure GUI":
                return
        except KeyError:
            pass
        self.color_map = get_color_map(self)
        self.map_image, self.map_shape = load_map_image(self)
        self.entities, self.tiles, self.entity_lookup_map = load_entities(self.color_map, self.map_image,
                                                                          self.map_shape)
        self.level_time = int(self.config["General"]["timelimit"])
        if self.name in level_backgrounds:
            self.background = level_backgrounds[self.name]
        else:
            self.background = level_backgrounds["Default"]

        return

    def kill_entity(self, entity):
        if entity in self.entities:
            self.entities.remove(entity)
        entity.get_behaviour(Collide).clear()
        entity.is_dead = True
        if entity.remain_on_reset:
            self.graveyard.append(entity)

    def revive_entities(self):
        self.entities.extend(self.graveyard)
        for entity in self.graveyard:
            entity.is_dead = False
        self.graveyard.clear()

    def get_entities(self, entity_name):
        if entity_name in self.entity_lookup_map:
            return self.entity_lookup_map[entity_name]
        raise Exception("Invalid entity!, " + entity_name)

    def get_y(self, number, unit):
        if unit == "percent":
            return self.map_shape[1] * number / 100
        return number

    def get_x(self, number, unit):
        if unit == "percent":
            return self.map_shape[0] * number / 100
        return number

    def spawn_entity(self, entity_class, x, y):
        entity_name = entity_class.__name__
        entity = entity_class(x, y, entity_name)
        self.entities.append(entity)
        if entity_name in self.entity_lookup_map:
            self.entity_lookup_map[entity_name].append(entity)
        else:
            self.entity_lookup_map[entity_name] = [entity]
        return entity

    def clear(self):
        for tile in self.tiles:
            tile.clear()
        self.tiles.clear()
        for entity in self.entities:
            entity.clear()
        self.entities.clear()
        self.entity_lookup_map.clear()

    def __del__(self):
        self.clear()
