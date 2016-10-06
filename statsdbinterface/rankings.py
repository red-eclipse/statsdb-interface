import time
from .database import models, extmodels
from .database.core import db
from .function_cache import cached
from . import redeclipse


def days_ago(days):
    return time.time() - (days * 60 * 60 * 24)


@cached(60)
def first_game_in_days(days):
    return (models.Game.query
            .with_entities(db.func.min(models.Game.id))
            .filter(models.Game.time >= days_ago(days)))


def weapon_sums(days):
    first_game = first_game_in_days(days)
    totalwielded = (models.GameWeapon.query
                    .with_entities(db.func.sum(
                        models.GameWeapon.timewielded))
                    .filter(models.GameWeapon.game_id >= first_game)
                    .first()[0])
    weapons = extmodels.Weapon.all_from_f(
        models.GameWeapon.game_id >= first_game)
    return {
         "weapons": weapons,
         "totalwielded": totalwielded or 0,
         }


@cached(15 * 60)
def weapons_by_wielded(days):
    """
    Return weapons sorted by wielded ratio.
    Cache can be high, result will not change quickly.
    """
    res = weapon_sums(days)
    ret = sorted(res["weapons"], key=lambda w: w.timewielded, reverse=True)
    return [{"name": w.name, "timewielded":
             w.timewielded / max(1, res["totalwielded"])} for w in ret]


@cached(60)
def maps_by_games(days):
    """
    Return maps sorted by their number of games.
    Cache should be low, result could change quickly.
    """
    maps = [r[0] for r in models.Game.query
            .with_entities(models.Game.map)
            .filter(models.Game.time >= days_ago(days))]
    ret = []
    for map_ in set(maps):
        ret.append({
            "name": map_,
            "games": maps.count(map_),
            })
    return sorted(ret, key=lambda m: m['games'], reverse=True)


@cached(60)
def players_by_games(days):
    first_game = first_game_in_days(days)
    players = [r[0] for r in models.GamePlayer.query
               .with_entities(models.GamePlayer.handle)
               .filter(models.GamePlayer.game_id >= first_game)
               .filter(models.GamePlayer.handle != "")]
    ret = []
    for player in set(players):
        ret.append({
            "handle": player,
            "games": players.count(player),
            })
    return sorted(ret, key=lambda p: p['games'], reverse=True)


@cached(60)
def servers_by_games(days):
    first_game = first_game_in_days(days)
    servers = [r[0] for r in models.GameServer.query
               .with_entities(models.GameServer.handle)
               .filter(models.GameServer.game_id >= first_game)
               .filter(models.GameServer.handle != "")]
    ret = []
    for server in set(servers):
        ret.append({
            "handle": server,
            "games": servers.count(server),
            })
    return sorted(ret, key=lambda p: p['games'], reverse=True)


@cached(5 * 60)
def players_by_dpm(days):
    """
    Return a sorted list of players with and by dpm.
    """
    first_game = first_game_in_days(days)
    res_compiled = {}
    players = (models.GamePlayer.query
               .with_entities(models.GamePlayer.handle)
               .filter(models.GamePlayer.game_id >= first_game)
               .filter(models.GamePlayer.handle != "")
               .group_by(models.GamePlayer.handle))
    for player in players:
        player = player[0]
        d1, d2, timewielded = (
            models.GameWeapon.query
            .with_entities(db.func.sum(models.GameWeapon.damage1),
                           db.func.sum(models.GameWeapon.damage2),
                           db.func.sum(models.GameWeapon.timewielded))
            .filter(models.GameWeapon.playerhandle == player)
            .filter(models.GameWeapon.game_id >= first_game)
            .filter(db.func.re_normal_weapons(models.GameWeapon.game_id))
            .filter(~models.GameWeapon.weapon.in_(
                redeclipse.versions.default.notwielded
                ))).first()
        res_compiled[player] = {
            "handle": player,
            "dpm": (((d1 or 0) + (d2 or 0)) / (max(timewielded or 0, 1) / 60)),
            }
    return [{
        "handle": res_compiled[p]['handle'],
        "dpm": res_compiled[p]['dpm'],
        } for p in sorted(
            res_compiled, key=lambda p: res_compiled[p]['dpm'], reverse=True)]


@cached(10 * 60)
def player_weapons(days):
    """
    Return a sorted list of weapons and their best players with the most FPM.
    """
    first_game = first_game_in_days(days)
    res = (models.GameWeapon.query
           .filter(models.GameWeapon.game_id >= first_game)
           .filter(models.GameWeapon.playerhandle != "")
           .filter(db.func.re_normal_weapons(models.GameWeapon.game_id))
           .filter(models.GameWeapon.weapon.in_(
               redeclipse.versions.default.standardweaponlist))).all()
    weapons = {}
    for weapon in redeclipse.versions.default.standardweaponlist:
        weapons[weapon] = {}
    for r in res:
        res_compiled = weapons[r.weapon]
        if r.playerhandle not in res_compiled:
            res_compiled[r.playerhandle] = {
                "handle": r.playerhandle,
                "frags": 0,
                "time": 0,
                }
        res_compiled[r.playerhandle]['frags'] += (r.frags1 + r.frags2)
        res_compiled[r.playerhandle]['time'] += (
            r.timeloadout
            if r.weapon in redeclipse.versions.default.notwielded
            else r.timewielded)
    for weapon in weapons:
        for h in weapons[weapon]:
            weapons[weapon][h]['fpm'] = (weapons[weapon][h]['frags'] /
                                         (max(weapons[weapon][h]['time'], 1) /
                                          60))
        weapons[weapon] = [{
            "handle": weapons[weapon][p]['handle'],
            "fpm": weapons[weapon][p]['fpm'],
            } for p in sorted(
                weapons[weapon], key=lambda p: weapons[weapon][p]['fpm'],
                reverse=True)]
    weapons_compiled = []
    for weapon in weapons:
        for player in weapons[weapon]:
            weapons_compiled.append({
                "weapon": weapon,
                "handle": player['handle'],
                "fpm": player['fpm'],
                })
    ret = []
    seen = []
    for entry in sorted(weapons_compiled,
                        key=lambda w: w['fpm'],
                        reverse=True):
        if entry['weapon'] in seen:
            continue
        seen.append(entry['weapon'])
        ret.append(entry)
    return ret
