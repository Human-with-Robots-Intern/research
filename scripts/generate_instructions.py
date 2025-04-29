from itertools import combinations, product
import json
from pathlib import Path
import random

def apply_filters(instruction_list):
    # Convert to set for faster lookup
    instruction_set = set(instruction_list)
    
    # Constraint 1: boil_potato and fill_pot_with_water cannot coexist
    if "boil_potato" in instruction_set and "fill_pot_with_water" in instruction_set:
        return False
    
    # Constraint 2: boil_potato and heat_the_potato_using_microwave cannot coexist
    if "boil_potato" in instruction_set and "heat_the_potato_using_microwave" in instruction_set:
        return False
    
    # Constraint 3: heat_the_bread_using_microwave and heat_the_potato_using_microwave cannot coexist
    if "heat_the_bread_using_microwave" in instruction_set and "heat_the_potato_using_microwave" in instruction_set:
        return False
    
    # Constraint 4: prepare_a_water_cup and make_a_coffee cannot coexist
    if "prepare_a_water_cup" in instruction_set and "make_a_coffee" in instruction_set:
        return False
    
    # Constraint 5: wash_apple_and_lettuce and put_apple_and_lettuce_in_fridge cannot coexist
    if "wash_apple_and_lettuce" in instruction_set and "put_apple_and_lettuce_in_fridge" in instruction_set:
        return False
    
    return True

def _generate_and_sample_instructions(base_list, combo_list, combo_size, max_samples=5):
    """Helper function to generate combinations, filter, format, and sample instructions."""
    temp_instructions = []
    for combo in combinations(combo_list, combo_size):
        instruction_list = base_list + list(combo)
        if apply_filters(instruction_list):
            instruction = " and ".join(instruction_list)
            temp_instructions.append(instruction)
    return random.sample(temp_instructions, min(max_samples, len(temp_instructions)))

def generate_simple_instructions(non_critical_list, not_constrained_list):
    """Generates simple instructions (1-2 non-critical + 4-5 not-constrained, total 6)."""
    simple_instructions = []
    
    # Case 1: 1 non-critical + 5 not-constrained
    if len(not_constrained_list) >= 5:
        for non_critical in non_critical_list:
            simple_instructions.extend(
                _generate_and_sample_instructions([non_critical], not_constrained_list, 5)
            )
            
    # Case 2: 2 non-critical + 4 not-constrained
    if len(non_critical_list) >= 2 and len(not_constrained_list) >= 4:
        for non_critical_combo in combinations(non_critical_list, 2):
             simple_instructions.extend(
                _generate_and_sample_instructions(list(non_critical_combo), not_constrained_list, 4)
            )

    return simple_instructions

def generate_normal_instructions(critical_list, non_critical_list, not_constrained_list):
    """Generates normal instructions (1 critical + 1 non-critical + 4 not-constrained, total 6)."""
    normal_instructions = []
    if len(not_constrained_list) >= 4:
        for critical_item in critical_list:
            for non_critical_item in non_critical_list:
                normal_instructions.extend(
                    _generate_and_sample_instructions([critical_item, non_critical_item], not_constrained_list, 4)
                )
    return normal_instructions

def generate_complicated_instructions(critical_list, non_critical_list, not_constrained_list):
    """Generates complicated instructions (2+ critical + 0-1 non-critical + 3 not-constrained, total 6)."""
    complicated_instructions = []

    # Case 1: 2 critical + 1 non-critical + 3 not-constrained
    if len(critical_list) >= 2 and len(not_constrained_list) >= 3:
        for critical_combo in combinations(critical_list, 2):
            for non_critical in non_critical_list:
                 complicated_instructions.extend(
                    _generate_and_sample_instructions(list(critical_combo) + [non_critical], not_constrained_list, 3)
                )

    # Case 2: 3 critical + 0 non-critical + 3 not-constrained
    if len(critical_list) >= 3 and len(not_constrained_list) >= 3:
        for critical_combo in combinations(critical_list, 3):
             complicated_instructions.extend(
                _generate_and_sample_instructions(list(critical_combo), not_constrained_list, 3)
            )
            
    return complicated_instructions

def generate_instructions(critical_list, non_critical_list, not_constrained_list):
    """Generates simple, normal, and complicated instructions based on input lists."""
    simple = generate_simple_instructions(non_critical_list, not_constrained_list)
    normal = generate_normal_instructions(critical_list, non_critical_list, not_constrained_list)
    complicated = generate_complicated_instructions(critical_list, non_critical_list, not_constrained_list)
    return simple, normal, complicated

Floorplan_kitchen_critical_list = [
    "boil_potato",
    "cook_egg",
    "fill_pot_with_water"
]

Floorplan_kitchen_non_critical_list = [
    "heat_the_bread_using_microwave",
    "make_a_coffee",
    "heat_the_potato_using_microwave"
]

Floorplan_kitchen_not_constrained_list = [
    "wash_apple_and_lettuce",
    "put_apple_and_lettuce_in_fridge",
    "wash_all_cutlery",
    "set_the_table",
    "prepare_a_water_cup",
    "wash_Spoon"
]

# Floorplan1
Floorplan1_critical_list = [
    "boil_potato", 
    "cook_egg",
    "fill_pot_with_water", 
    "boil_water_with_kettle", 
    "fill_water_inside_the_bottle"
]
Floorplan1_non_critical_list = [
    "heat_the_bread_using_microwave", 
    "make_a_coffee", 
    "heat_the_potato_using_microwave"
]
Floorplan1_not_constrained_list = [
    "wash_apple_and_lettuce", 
    "put_apple_and_lettuce_in_fridge", 
    "prepare_a_water_cup", 
    "wash_all_cutlery", 
    "throw_away_paper_towel_roll", 
    "put_the_wine_bottle_inside_a_cabinet", 
    "put_the_creditcard_on_the_countertop", 
    "put_the_book_in_cabinet", 
    "set_the_table"
]

# Floorplan7
Floorplan7_critical_list = [
    "boil_potato", 
    "cook_egg",
    "fill_pot_with_water", 
    "boil_water_with_kettle"
]
Floorplan7_non_critical_list = [
    "heat_the_bread_using_microwave", 
    "make_a_coffee", 
    "heat_the_potato_using_microwave"
]
Floorplan7_not_constrained_list = [
    "wash_apple_and_lettuce", 
    "put_apple_and_lettuce_in_fridge", 
    "wash_all_cutlery", 
    "set_the_table", 
    "put_the_wine_bottle_inside_a_cabinet", 
    "put_a_statue_on_the_table"
]

# Floorplan13
Floorplan13_critical_list = [
    "boil_potato", 
    "cook_egg",
    "fill_pot_with_water"
]
Floorplan13_non_critical_list = [
    "heat_the_bread_using_microwave", 
    "make_a_coffee", 
    "heat_the_potato_using_microwave"
]
Floorplan13_not_constrained_list = [
    "wash_apple_and_lettuce", 
    "put_apple_and_lettuce_in_fridge", 
    "wash_all_cutlery", 
    "set_the_table", 
    "throw_away_paper_towel_roll", 
    "put_the_pencil_on_somewhere"
]

# Floorplan18
Floorplan18_critical_list = [
    "boil_potato", 
    "cook_egg",
    "fill_pot_with_water",
    "boil_water_with_kettle"
]
Floorplan18_non_critical_list = [
    "heat_the_bread_using_microwave", 
    "make_a_coffee", 
    "heat_the_potato_using_microwave"
]
Floorplan18_not_constrained_list = [
    "wash_apple_and_lettuce", 
    "put_apple_and_lettuce_in_fridge", 
    "wash_all_cutlery", 
    "set_the_table", 
    "throw_away_paper_towel_roll", 
    "roll_up_down_the_blinds", 
    "put_something_inside_the_safe"
]

# Floorplan27
Floorplan27_critical_list = [
    "boil_potato", 
    "cook_egg",
    "fill_pot_with_water"
]
Floorplan27_non_critical_list = [
    "heat_the_bread_using_microwave", 
    "make_a_coffee", 
    "heat_the_potato_using_microwave"
]
Floorplan27_not_constrained_list = [
    "wash_apple_and_lettuce", 
    "put_apple_and_lettuce_in_fridge", 
    "wash_all_cutlery", 
    "set_the_table", 
    "wash_two_ladles", 
    "put_the_wine_bottle_inside_a_cabinet"
]

# Floorplan_bathroom
Floorplan_bathroom_critical_list = [
    "fill_bathtub_with_water_with_shower_head",
    "clean_the_toilet"
]

Floorplan_bathroom_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]

Floorplan_bathroom_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain"
]

# Floorplan401
Floorplan401_critical_list = [
    "fill_bathtub_with_water_with_shower_head",    
    "clean_the_toilet", 
    "clean_the_sink",
]
Floorplan401_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]
Floorplan401_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain"
]

# Floorplan415
Floorplan415_critical_list = [
    "fill_bathtub_with_water_with_shower_head",
    "clean_the_toilet",
]
Floorplan415_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]
Floorplan415_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain"
]

# Floorplan422
Floorplan422_critical_list = [
    "fill_bathtub_with_water_with_shower_head",
    "clean_the_toilet",
]
Floorplan422_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]
Floorplan422_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain",
    "put_soap_bar_in_a_cabinet",
    "put_tissue_box_inside_the_drawer",
    "throw_away_empty_toilet_paper_on_the_counter_top"
]

# Floorplan426
Floorplan426_critical_list = [
    "fill_bathtub_with_water_with_shower_head",
    "clean_the_toilet",
]
Floorplan426_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]
Floorplan426_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain",
    "put_soap_bar_in_a_cabinet",
    "put_tissue_box_inside_the_drawer",
    "throw_away_empty_toilet_paper_on_the_counter_top"
]
# Floorplan427
Floorplan427_critical_list = [
    "fill_bathtub_with_water_with_shower_head",
    "clean_the_toilet",
    "clean_the_sink",
]   
Floorplan427_non_critical_list = [
    "wet_the_handtowel_with_water",
    "wet_the_towel_with_water"
]
Floorplan427_not_constrained_list = [
    "place_toilet_paper_on_the_toilet_paper_holder",
    "turn_on_the_candle",
    "trun_on_the_light",
    "throw_away_cloth",
    "close_shower_curtain",
    "put_tissue_box_inside_a_drawer",
    "put_a_soap_bar_on_the_sink",
    "put_the_candle_inside_the_drawer",
]

# Generate instructions for each floorplan
floorplans = {
    "Floorplan_kitchen": (Floorplan_kitchen_critical_list, Floorplan_kitchen_non_critical_list, Floorplan_kitchen_not_constrained_list),
    "Floorplan1": (Floorplan1_critical_list, Floorplan1_non_critical_list, Floorplan1_not_constrained_list),
    "Floorplan7": (Floorplan7_critical_list, Floorplan7_non_critical_list, Floorplan7_not_constrained_list),
    "Floorplan13": (Floorplan13_critical_list, Floorplan13_non_critical_list, Floorplan13_not_constrained_list),
    "Floorplan18": (Floorplan18_critical_list, Floorplan18_non_critical_list, Floorplan18_not_constrained_list),
    "Floorplan27": (Floorplan27_critical_list, Floorplan27_non_critical_list, Floorplan27_not_constrained_list),
    "Floorplan_bathroom": (Floorplan_bathroom_critical_list, Floorplan_bathroom_non_critical_list, Floorplan_bathroom_not_constrained_list),
    "Floorplan401": (Floorplan401_critical_list, Floorplan401_non_critical_list, Floorplan401_not_constrained_list),
    "Floorplan415": (Floorplan415_critical_list, Floorplan415_non_critical_list, Floorplan415_not_constrained_list),
    "Floorplan422": (Floorplan422_critical_list, Floorplan422_non_critical_list, Floorplan422_not_constrained_list),
    "Floorplan426": (Floorplan426_critical_list, Floorplan426_non_critical_list, Floorplan426_not_constrained_list),
    "Floorplan427": (Floorplan427_critical_list, Floorplan427_non_critical_list, Floorplan427_not_constrained_list),
}

# Generate instructions for each floorplan and store in a dictionary
instructions_dict = {}
for floorplan_name, (critical, non_critical, not_constrained) in floorplans.items():
    simple, normal, complicated = generate_instructions(critical, non_critical, not_constrained)
    
    instructions_dict[floorplan_name] = {
        "simple": [f"{instruction}" for instruction in simple],
        "normal": [f"{instruction}" for instruction in normal],
        "complicated": [f"{instruction}" for instruction in complicated]
    }

# Create the final dictionary structure
output_dict = {"instructions": instructions_dict}

# Get the current file's directory
current_dir = Path(__file__).parent

# Save to JSON file
output_path = current_dir / "instructions.json"
with open(output_path, 'w') as f:
    json.dump(output_dict, f, indent=4) 