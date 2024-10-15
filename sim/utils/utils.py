def two_dict_equal(dict1, dict2, threshold=0.001, ignore_keys=[]):
    if len(dict1) != len(dict2):
        print("different len", dict1, dict2)
        return False
    # assert len(dict1) == len(dict2), print('different len', dict1, dict2)
    equal = True
    for k in dict1:
        if k in ignore_keys:
            continue
        val1 = dict1[k]
        val2 = dict2[k]
        if not (
            type(val1) == type(val2)
            or (type(val1) in [int, float] and type(val2) in [int, float])
        ):
            print("different type", dict1, dict2)
            return False
        # assert type(val1) == type(val2) or (type(val1) in [int, float] and type(val2) in [int, float]), ()
        if type(val1) == dict:
            equal = two_dict_equal(val1, val2)
        elif type(val1) == list:
            equal = two_list_equal(val1, val2)
        # elif val1 != val1: # Either nan or -inf
        #     equal = val2 != val2
        elif type(val1) == float:
            equal = abs(val1 - val2) < threshold
        else:
            equal = val1 == val2
        if not equal:
            print("not equal", "key", k, "values", val1, val2)
            return equal
    return equal


def two_list_equal(l1, l2):
    dict1 = {i: v for (i, v) in enumerate(l1)}
    dict2 = {i: v for (i, v) in enumerate(l2)}
    return two_dict_equal(dict1, dict2)
