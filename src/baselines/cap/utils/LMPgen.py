from openai import OpenAI

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

# imports for LMPs
import shapely
import ast
import astunparse
from time import sleep

import os
base_dir = os.path.dirname(os.path.abspath(__file__))


import numpy as np

import json

client = OpenAI(
    api_key="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"
)

log_file = open(os.path.join(base_dir, "../result/cap_plan.txt"), "w", buffering=1)


class LMP:

    def __init__(self, name, cfg, lmp_fgen, fixed_vars, variable_vars):
        self._name = name
        self._cfg = cfg

        self._base_prompt = self._cfg["prompt_text"]

        self._stop_tokens = list(self._cfg["stop"])

        self._lmp_fgen = lmp_fgen

        self._fixed_vars = fixed_vars
        self._variable_vars = variable_vars
        self.exec_hist = ""

    def clear_exec_hist(self):
        self.exec_hist = ""

    def build_prompt(self, query, context=""):
        if len(self._variable_vars) > 0:
            # 할수 있는 함수들 정의한거 str 로 묶기.
            variable_vars_imports_str = (
                f"from utils import {', '.join(self._variable_vars.keys())}"
            )
        else:
            variable_vars_imports_str = ""

        prompt = self._base_prompt.replace(
            "{variable_vars_imports}", variable_vars_imports_str
        )

        if self._cfg["maintain_session"]:
            # 시뮬레이션 실행 기록 저장하기
            prompt += f"\n{self.exec_hist}"

        if context != "":
            # context 가 빈 문자열이 아니라면 prompt 에 추가
            prompt += f"\n{context}"

        # "query_prefix": "# ",
        # "query_suffix": ".",
        # "query_prefix": "# define function: ",
        # "query_suffix": ".", 이건거.
        use_query = f'{self._cfg["query_prefix"]}{query}{self._cfg["query_suffix"]}'
        # query 추가하기
        prompt += f"\n{use_query}"

        # prompt 랑 use_query 반환하기.
        return prompt, use_query

    def __call__(self, query, context="", **kwargs):
        # __call__ 은 class를 함수처럼 사용할 때 불러와지는거임. 원래는 class 정의한 다음에 class.fun(123) 이런식인데 얘는 class(123) 이렇게 부르는거 가능
        prompt, use_query = self.build_prompt(query, context=context)
        sys_guide = """You are a highly intelligent and context-aware Household AI Robot Assistant.
        """
        guide = """
        You must honor what is written in the note unconditionally.
        ## [Notes]
        1. The # is a directive, and anything that follows it is code. When you see a directive, generate the Python code for it.
        2. DO NOT include triple quotes (```) or the word 'python' in your response.
        3. Never send me an empty python block.
        4. Never include 'import'.

        ## [EXAMPLES]
        """
        prompt = [
            {"role": "system", "content": f"{sys_guide}"},
            {"role": "user", "content": f"{guide}" f"{prompt}"},
        ]
        while True:
            try:
                code_str = client.chat.completions.create(
                    messages=prompt,
                    # stop=self._stop_tokens,
                    temperature=self._cfg["temperature"],
                    model="gpt-4o",
                    max_tokens=self._cfg["max_tokens"],
                )
                code_str = code_str.choices[0].message.content.strip()
                code_str = code_str.replace("python", "")
                code_str = code_str.replace("```", "")
                break
            except:
                print("code_str error")
            # except (RateLimitError, APIConnectionError) as e:
            #     print(f'OpenAI API got err {e}')
            #     print('Retrying after 10s.')
            #     sleep(10)

        # 'include_context' : True 이고 그 context 가 빈 문자열이 아니라면
        if self._cfg["include_context"] and context != "":
            # context
            # code_str
            to_exec = f"{context}\n{code_str}"
            # context
            # use_query
            # code_str
            to_log = f"{context}\n{use_query}\n{code_str}"
        else:
            to_exec = code_str
            to_log = f"{use_query}\n{to_exec}"

        log_file.write(to_log)
        to_log_pretty = highlight(to_log, PythonLexer(), TerminalFormatter())
        print(f"LMP {self._name} exec:\n\n{to_log_pretty}\n")

        """ 이런식으로 나옴
        LMP parse_position exec:

        # a point 10cm to the left of the brown bowl.

        bowl_name = parse_obj_name('the brown bowl', f'objects = {get_obj_names()}')
        bowl_pos = get_obj_pos(bowl_name)
        left_pos = bowl_pos + [-0.1, 0]
        ret_val = left_pos
        """
        # code_str 에 새로운 함수가 있다면 생성
        new_fs = self._lmp_fgen.create_new_fs_from_code(code_str)
        # 함수 생성되었으니 variable_vars 에 추가
        self._variable_vars.update(new_fs)

        # dicts 를 list로 주면 다 순회해서 key: value 쌍으로 만들어서 다시 던져줌
        gvars = merge_dicts([self._fixed_vars, self._variable_vars])
        lvars = kwargs

        if not self._cfg["debug_mode"]:
            # debug_mode 가 아니라면....")
            exec_safe(to_exec, gvars, lvars)

        self.exec_hist += f"\n{to_exec}"

        if self._cfg["maintain_session"]:
            self._variable_vars.update(lvars)

        if self._cfg["has_return"]:
            return lvars[self._cfg["return_val_name"]]


class LMPFGen:

    def __init__(self, cfg, fixed_vars, variable_vars):
        self._cfg = cfg

        self._stop_tokens = list(self._cfg["stop"])
        self._fixed_vars = fixed_vars
        self._variable_vars = variable_vars

        self._base_prompt = self._cfg["prompt_text"]

    def create_f_from_sig(
        self, f_name, f_sig, other_vars=None, fix_bugs=False, return_src=False
    ):
        print(f"Creating function: {f_sig}")

        use_query = f'{self._cfg["query_prefix"]}{f_sig}{self._cfg["query_suffix"]}'
        prompt = f"{self._base_prompt}\n{use_query}"
        sys_guide = """You are a highly intelligent and context-aware Household AI Robot Assistant.
        """
        guide = """## [TASK]
        1. The # is a directive, and anything that follows it is code. When you see a directive, generate the Python code for it.
        2. Do not include triple quotes (```) or the word 'python' in your response.
        3. Do not send blank
        
        ## [EXAMPLES]
        """
        prompt = [
            {"role": "system", "content": f"{sys_guide}"},
            {"role": "user", "content": f"{guide}" f"{prompt}"},
        ]

        while True:
            try:
                f_src = (
                    client.chat.completions.create(
                        messages=prompt,
                        stop=self._stop_tokens,
                        temperature=self._cfg["temperature"],
                        model="gpt-4o",
                        max_tokens=self._cfg["max_tokens"],
                    )
                    .choices[0]
                    .message.content.strip()
                )
                f_src = f_src.replace("python", "")
                f_src = f_src.replace("```", "")
                break
            except:
                print("f_src error")
            # except (RateLimitError, APIConnectionError) as e:
            #     print(f'OpenAI API got err {e}')
            #     print('Retrying after 10s.')
            #     sleep(10)

        if fix_bugs:
            prompt = (
                "# "
                + f_src
                + "Fix the bug if there is one. Improve readability. Keep same inputs and outputs. Only small changes. No comments."
            )
            prompt = [{"role": "user", "content": prompt}]
            f_src = (
                client.chat.completions.create(
                    model="gpt-4o", temperature=0, messages=prompt
                )
                .choices[0]
                .message.content.strip()
            )
            f_src = f_src.replace("python", "")
            f_src = f_src.replace("```", "")

        if other_vars is None:
            other_vars = {}
        gvars = merge_dicts([self._fixed_vars, self._variable_vars, other_vars])
        lvars = {}

        exec_safe(f_src, gvars, lvars)

        f = lvars[f_name]

        to_print = highlight(
            f"{use_query}\n{f_src}", PythonLexer(), TerminalFormatter()
        )
        log_file.write(to_print)
        print(f"LMP FGEN created:\n\n{to_print}\n")

        if return_src:
            return f, f_src
        return f

    def create_new_fs_from_code(
        self, code_str, other_vars=None, fix_bugs=False, return_src=False
    ):
        fs, f_assigns = {}, {}
        f_parser = FunctionParser(fs, f_assigns)
        f_parser.visit(ast.parse(code_str))
        for f_name, f_assign in f_assigns.items():
            if f_name in fs:
                fs[f_name] = f_assign

        if other_vars is None:
            other_vars = {}

        new_fs = {}
        srcs = {}
        for f_name, f_sig in fs.items():
            all_vars = merge_dicts(
                [self._fixed_vars, self._variable_vars, new_fs, other_vars]
            )
            if not var_exists(f_name, all_vars):
                f, f_src = self.create_f_from_sig(
                    f_name, f_sig, new_fs, fix_bugs=fix_bugs, return_src=True
                )

                # recursively define child_fs in the function body if needed
                f_def_body = astunparse.unparse(ast.parse(f_src).body[0].body)
                child_fs, child_f_srcs = self.create_new_fs_from_code(
                    f_def_body, other_vars=all_vars, fix_bugs=fix_bugs, return_src=True
                )

                if len(child_fs) > 0:
                    new_fs.update(child_fs)
                    srcs.update(child_f_srcs)

                    # redefine parent f so newly created child_fs are in scope
                    gvars = merge_dicts(
                        [self._fixed_vars, self._variable_vars, new_fs, other_vars]
                    )
                    lvars = {}

                    exec_safe(f_src, gvars, lvars)

                    f = lvars[f_name]

                new_fs[f_name], srcs[f_name] = f, f_src

        if return_src:
            return new_fs, srcs
        return new_fs


class FunctionParser(ast.NodeTransformer):

    def __init__(self, fs, f_assigns):
        super().__init__()
        self._fs = fs
        self._f_assigns = f_assigns

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name):
            f_sig = astunparse.unparse(node).strip()
            f_name = astunparse.unparse(node.func).strip()
            self._fs[f_name] = f_sig
        return node

    def visit_Assign(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call):
            assign_str = astunparse.unparse(node).strip()
            f_name = astunparse.unparse(node.value.func).strip()
            self._f_assigns[f_name] = assign_str
        return node


def var_exists(name, all_vars):
    try:
        eval(name, all_vars)
    except:
        exists = False
    else:
        exists = True
    return exists


def merge_dicts(dicts):
    return {k: v for d in dicts for k, v in d.items()}


def exec_safe(code_str, gvars=None, lvars=None):
    banned_phrases = ["import", "__"]
    for phrase in banned_phrases:
        assert phrase not in code_str

    if gvars is None:
        gvars = {}
    if lvars is None:
        lvars = {}
    empty_fn = lambda *args, **kwargs: None
    custom_gvars = merge_dicts([gvars, {"exec": empty_fn, "eval": empty_fn}])
    exec(code_str, custom_gvars, lvars)


## LMP Wrapper


class LMP_wrapper:
    # env는 PickNPlace env 임
    def __init__(self, controller, cfg, render=False):
        self.controller = controller
        self._cfg = cfg
        self.object_names = list(
            set(
                obj["objectType"].lower
                for obj in controller.step("Pass").metadata["objects"]
            )
        )
        self.render = render

    # "get_obj_pos",
    # "is_obj_visible",
    # "get_obj_names"

    def is_obj_visible(self, obj_name):
        data = self.controller.step("Pass").metadata["objects"]
        obj_ids = list([obj["objectType"].lower() for obj in data if obj["visible"]])
        return obj_name in obj_ids

    def get_obj_names(self):
        return self.object_names[::]

    def get_obj_id(self, obj_name):
        hmm = open("hmm_log.txt", "w", buffering=1)
        for obj in self.controller.last_event.metadata["objects"]:
            hmm.write(
                f"{obj['objectType'].lower()} == {obj_name}: {obj['objectType'].lower() == obj_name}\n"
            )
            if obj["objectType"].lower() == obj_name:
                return obj["objectId"]
        return None

    def get_true_states(self, obj_id):
        properties = [
            "isInteractable",
            "isToggled",
            "isBroken",
            "isFilledWithLiquid",
            "isDirty",
            "isUsedUp",
            "isCooked",
            "isHeatSource",
            "isColdSource",
            "isSliced",
            "isOpen",
            "isPickedUp",
            "isMoving",
        ]
        id = obj_id
        true_state = []
        data = self.controller.step("Pass").metadata["objects"]
        for obj in data:
            if obj["objectId"] == id:
                for prop in properties:
                    if obj[prop]:
                        true_state.append(prop)
                break
        print(f"{true_state=}")
        return true_state

    def get_ability_states(self, obj_id):
        properties = [
            "toggleable",
            "breakable",
            "canFillWithLiquid",
            "dirtyable",
            "canBeUsedUp",
            "cookable",
            "sliceable",
            "openable",
            "pickupable",
        ]
        id = obj_id
        ability_state = []
        data = self.controller.step("Pass").metadata["objects"]

        for obj in data:
            if obj["objectId"] == id:
                for prop in properties:
                    if obj[prop]:
                        ability_state.append(prop)
                break
        return ability_state

    def get_parentReceptacles(self, obj_id):
        data = self.controller.step("Pass").metadata["objects"]
        parentReceptacles = []
        for obj in data:
            if obj["objectId"] == obj_id:
                parentReceptacles = obj["parentReceptacles"]
                break
        print(f"{parentReceptacles=}")
        return parentReceptacles

    def get_obj_in_hand(self):
        data = self.controller.last_event.metadata["objects"]
        for obj in data:
            if obj["isPickedUp"] == True:
                return obj["objectId"]
