"""
OpenFront RTS Strategy Engine
Decision layer prioritized by:
1. Early expansion (unclaimed neutral territory)
2. Economy (ports, factories, resource generation)
3. Military buildup (troop reserves, defense)
4. Strategic offensive strikes (nukes, target player conquests)
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class Action:
    type: str  # "expand", "build", "attack", "ally", "pass"
    params: Dict[str, Any]


class OpenFrontStrategyEngine:
    """Evaluates structured game state and produces strategic RTS decisions."""

    def decide_next_action(self, state: Dict[str, Any]) -> Action:
        """
        Decision logic prioritizing:
        Early expansion -> Economy -> Military buildup -> Strategic nukes.
        """
        territory = state.get("territory", 1)
        population = state.get("population", 100)
        gold = state.get("gold", 50)
        troops = state.get("troops", 10)
        nukes = state.get("nukes", 0)
        enemies = state.get("enemies", [])
        unclaimed_tiles = state.get("unclaimed_tiles", [])
        factories = state.get("factories", 0)
        ports = state.get("ports", 0)

        # 1. Early Expansion: expand if neutral territory is nearby and territory < 30
        if territory < 30 and unclaimed_tiles:
            target_tile = unclaimed_tiles[0]
            direction = target_tile.get("direction", "north")
            return Action(type="expand", params={"direction": direction, "tile_id": target_tile.get("id")})

        # 2. Economy: build factories/ports if gold is available
        if gold >= 100 and (factories + ports < 10):
            building_type = "port" if state.get("has_coast", False) and ports < 3 else "factory"
            return Action(type="build", params={"building_type": building_type, "location": "capital"})

        # 3. Strategic Nukes: if enemy capital detected and nuke ready
        if nukes > 0 and enemies:
            high_threat_enemy = max(enemies, key=lambda e: e.get("strength", 0))
            if high_threat_enemy.get("strength", 0) > troops * 0.8:
                return Action(type="attack", params={
                    "target_player": high_threat_enemy.get("id", "enemy"),
                    "ratio": 1.0,
                    "use_nuke": True
                })

        # 4. Military Buildup / Attack:
        if troops > 50 and enemies:
            weakest_enemy = min(enemies, key=lambda e: e.get("strength", 9999))
            if troops > weakest_enemy.get("strength", 0) * 1.5:
                return Action(type="attack", params={
                    "target_player": weakest_enemy.get("id", "enemy"),
                    "ratio": 0.5,
                    "use_nuke": False
                })

        # Default: expand or recruit troops
        if unclaimed_tiles:
            return Action(type="expand", params={"direction": unclaimed_tiles[0].get("direction", "east")})

        return Action(type="pass", params={})
