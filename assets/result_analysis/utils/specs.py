from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ObjectCondition:
    """Object condition with name prefix matching and required properties."""

    object_name_prefix: str
    required_properties: Mapping[str, Any]


@dataclass(frozen=True)
class ConditionGroup:
    """A set of object conditions that must be true simultaneously in a step."""

    objects: Sequence[ObjectCondition]


@dataclass(frozen=True)
class TaskSpec:
    """Specification to evaluate a task's GCR/TSR."""

    name: str
    gcr_end: Optional[ConditionGroup] = None
    gcr_mid_groups: Optional[Sequence[ConditionGroup]] = None
    tsr_trigger: Optional[ConditionGroup] = None
    tsr_end: Optional[ConditionGroup] = None


def OC(name_prefix: str, **props: Any) -> ObjectCondition:
    """Helper to build ObjectCondition."""

    return ObjectCondition(object_name_prefix=name_prefix, required_properties=props)


def CG(*objs: ObjectCondition) -> ConditionGroup:
    """Helper to build ConditionGroup."""

    return ConditionGroup(objects=list(objs))


TASK_SPECS: Dict[str, TaskSpec] = {
    # boil_potato
    "boil_potato": TaskSpec(
        name="boil_potato",
        gcr_end=CG(OC("potato", isCooked=True)),
        gcr_mid_groups=[
            CG(
                # OC("potato", parentReceptacles=["pot"]),
                OC("pot", isFilledWithLiquid=True, parentReceptacles=["stove"]),
                OC("stoveknob", isToggled=True),
            )
        ],
        tsr_trigger=CG(
            # OC("potato", parentReceptacles=["pot"]),
            OC("potato", isCooked=True),
            OC("pot", isFilledWithLiquid=True, parentReceptacles=["stove"]),
            OC("stoveknob", isToggled=True),
        ),
        tsr_end=CG(OC("stoveknob", isToggled=False)),
    ),
    # boil_water_with_pot
    "boil_water_with_pot": TaskSpec(
        name="boil_water_with_pot",
        gcr_end=CG(OC("pot", isFilledWithLiquid=True)),
        gcr_mid_groups=[
            CG(
                OC("pot", isFilledWithLiquid=True, parentReceptacles=["stove"]),
                OC("stoveknob", isToggled=True),
            )
        ],
        tsr_trigger=CG(
            OC("pot", isFilledWithLiquid=True, parentReceptacles=["stove"]),
            OC("stoveknob", isToggled=True),
        ),
        tsr_end=CG(OC("stoveknob", isToggled=False)),
    ),
    # fill_pot_with_water
    "fill_pot_with_water": TaskSpec(
        name="fill_pot_with_water",
        gcr_end=CG(OC("pot", isFilledWithLiquid=True)),
        gcr_mid_groups=[CG(OC("pot", isFilledWithLiquid=True))],
        tsr_trigger=CG(
            OC("pot", isFilledWithLiquid=True, parentReceptacles=["sink"]),
            OC("faucet", isToggled=True),
        ),
        tsr_end=CG(OC("faucet", isToggled=False)),
    ),
    # fill_bowl_with_water
    "fill_bowl_with_water": TaskSpec(
        name="fill_bowl_with_water",
        gcr_end=CG(OC("bowl", isFilledWithLiquid=True)),
        gcr_mid_groups=[CG(OC("bowl", isFilledWithLiquid=True))],
        tsr_trigger=CG(
            OC("bowl", isFilledWithLiquid=True, parentReceptacles=["sink"]),
            OC("faucet", isToggled=True),
        ),
        tsr_end=CG(OC("faucet", isToggled=False)),
    ),
    # heat_the_bread_using_microwave
    "heat_the_bread_using_microwave": TaskSpec(
        name="heat_the_bread_using_microwave",
        gcr_end=None,
        gcr_mid_groups=[CG(OC("bread", parentReceptacles=["microwave"]), OC("microwave", isToggled=True))],
        tsr_trigger=CG(OC("bread", parentReceptacles=["microwave"]), OC("microwave", isToggled=True)),
        tsr_end=CG(OC("microwave", isToggled=False)),
    ),
    # heat_the_potato_using_microwave
    "heat_the_potato_using_microwave": TaskSpec(
        name="heat_the_potato_using_microwave",
        gcr_end=None,
        gcr_mid_groups=[CG(OC("potato", parentReceptacles=["microwave"]), OC("microwave", isToggled=True))],
        tsr_trigger=CG(OC("potato", parentReceptacles=["microwave"]), OC("microwave", isToggled=True)),
        tsr_end=CG(OC("microwave", isToggled=False)),
    ),
    # make_a_coffee (명세 없음)
    "make_a_coffee": TaskSpec(
        name="make_a_coffee",
        gcr_end=None,
        gcr_mid_groups=None,
        tsr_trigger=None,
        tsr_end=None,
    ),
    # cook_egg
    "cook_egg": TaskSpec(
        name="cook_egg",
        gcr_end=CG(OC("egg_sliced", isCooked=True)),
        gcr_mid_groups=[
            CG(
                # OC("egg_sliced", parentReceptacles=["pan"]),
                OC("pan", parentReceptacles=["stove"]),
                OC("stoveknob", isToggled=True),
            )
        ],
        tsr_trigger=CG(
            OC("egg_sliced", parentReceptacles=["pan"]),
            OC("pan", parentReceptacles=["stove"]),
            OC("stoveknob", isToggled=True),
        ),
        tsr_end=CG(OC("stoveknob", isToggled=False)),
    ),
    # put_apple_and_lettuce_in_fridge
    "put_apple_and_lettuce_in_fridge": TaskSpec(
        name="put_apple_and_lettuce_in_fridge",
        gcr_end=CG(
            OC("apple", parentReceptacles=["fridge"]),
            OC("lettuce", parentReceptacles=["fridge"]),
        ),
        gcr_mid_groups=None,
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_a_tomato
    "wash_a_tomato": TaskSpec(
        name="wash_a_tomato",
        gcr_end=None,
        gcr_mid_groups=[CG(OC("tomato", parentReceptacles=["sink"]), OC("faucet", isToggled=True))],
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_a_butterknife
    "wash_a_butterknife": TaskSpec(
        name="wash_a_butterknife",
        gcr_end=None,
        gcr_mid_groups=[CG(OC("butterknife", parentReceptacles=["sink"]), OC("faucet", isToggled=True))],
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_a_spatula
    "wash_a_spatula": TaskSpec(
        name="wash_a_spatula",
        gcr_end=None,
        gcr_mid_groups=[CG(OC("spatula", parentReceptacles=["sink"]), OC("faucet", isToggled=True))],
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_all_fork_and_spoon (각각 독립 그룹 2개)
    "wash_all_fork_and_spoon": TaskSpec(
        name="wash_all_fork_and_spoon",
        gcr_end=None,
        gcr_mid_groups=[
            CG(OC("fork", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
            CG(OC("spoon", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
        ],
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_plate_and_cup (각각 독립 그룹 2개)
    "wash_plate_and_cup": TaskSpec(
        name="wash_plate_and_cup",
        gcr_end=None,
        gcr_mid_groups=[
            CG(OC("plate", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
            CG(OC("cup", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
        ],
        tsr_trigger=None,
        tsr_end=None,
    ),
    # wash_apple_and_lettuce (각각 독립 그룹 2개)
    "wash_apple_and_lettuce": TaskSpec(
        name="wash_apple_and_lettuce",
        gcr_end=None,
        gcr_mid_groups=[
            CG(OC("apple", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
            CG(OC("lettuce", parentReceptacles=["sink"]), OC("faucet", isToggled=True)),
        ],
        tsr_trigger=None,
        tsr_end=None,
    ),
}


