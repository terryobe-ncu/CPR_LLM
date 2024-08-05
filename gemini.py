# coding: utf8
import os
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError
from os.path import join as pj
import json

API_KEY = 'YOUR_API_KEY'

# ### PROMPTS
PERSONA_PROMPT = "我有一個商品，請根據以下的商品特色，幫我寫一段不超過20字的故事情節，要有性別跟年齡，只能包含會購買%s的原因、動機，但他還不知道此產品：\n"
CHOOSE_TARGET_PROMPT = "下列有%d個不同商品，每個商品有%d個商品特色及一位顧客的情境：\n\n%s\n請從中選出一個商品的其中一個特色，是最符合該顧客的情境。該特色必須明確易懂，不能包含廣告性內容，特色的文字不能和顧客情境一模一樣，並且沒有其他商品有類似的特色。格式為：\nX-0\n(理由。該特色為什麼吸引人?解決顧客的什麼問題?)"
USER_SIMULATION_PROMPT = "請扮演「%s」這樣的角色，向電商客服詢問%s的推薦。"

ACT_USER_PROMPT = "請扮演「%s」這樣情境的顧客，向電商客服簡單說明您的需求，並詢問%s的推薦，不可以說出自己的姓名。"
ACT_USER_INSTRUCTION = "當銷售員推薦[商品%s]時，請接受並對該商品的其它特色進行討論，不得尋求其它推薦；若銷售員推薦其它商品，請說明任意理由並拒絕，同時詢問是否有其它商品。你必須重複拒絕直到目標商品被推薦出來。"
SAMPLE_PERSONA_AND_TYPE = "一位45歲的女性，因擔心心血管健康，積極尋找能改善膽固醇和三酸甘油脂的保健品。", "保健品"
SAMPLE_USER_QUESTION = "我擔心膽固醇過高會有心血管問題，你推薦哪個保健品?"

ASSISTANT_PROMPT = "以下是%d個%s商品分別的特色：\n%s" + \
                   "請扮演一位專業的電商銷售客服，回答時舉出1個與顧客情境最相關的商品特色來進行推薦。每次提到商品時，以[商品X]顯示；提到商品特色時，以[X-0]顯示。絕對不能將商品特色的文字內容寫出來。"
ASSISTANT_TASK_AGREE = "好的，我絕對不會寫出商品特色的文字內容，而是改成使用代號。以下是我的範例回覆：\n向您推薦[商品X]，它的特色[X-0]能幫助您解決問題。"

# Gemini Configs
genai.configure(api_key=API_KEY)
MODEL = genai.GenerativeModel('gemini-1.0-pro')  # gemini-pro is an alias for gemini-1.0-pro
CONFIG = genai.types.GenerationConfig(temperature=0.)
# safety types
SAFETY_SETTINGS = {7: 'BLOCK_NONE', 9: 'BLOCK_NONE'}  # HARM_CATEGORY_HARASSMENT, HARM_CATEGORY_SEXUALLY_EXPLICIT

# Dir Configs
SOURCE_DIR = 'crawl'  # Grouped data
DATA_DIR = 'output'  # All output of this code is placed here
if not os.path.exists(DATA_DIR):
    os.mkdir(DATA_DIR)
GOODS_DIR = pj(DATA_DIR, 'goods')
if not os.path.exists(GOODS_DIR):
    os.mkdir(GOODS_DIR)

TARGET_DIR = 'output/target'
QUESTION_DIR = 'output/question'
CONVERSATION_DIR = 'output/conversation'


def stem_name(path: str) -> str:
    """:return: basename without extension"""
    base_name = os.path.basename(path)
    return base_name[: base_name.rfind('.')]


def dump_json(data, file_path):
    with open(file_path, 'w', encoding='utf8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
    print(file_path, "saved!")


def load_json(file_path):
    with open(file_path, encoding='utf8') as file:
        data = json.load(file)
    return data


class Utils:
    @staticmethod
    def create_message(question):
        return [{'role': 'user', 'parts': [question]}]

    @staticmethod
    def print_message(message, response_text=''):
        for d in message:
            s = d['parts'][0]
            if d['role'] == 'model':
                s = '\33[93m' + s + '\33[0m'  # yellow
            print(s)
        print('\33[93m' + response_text + '\33[0m')  # yellow

    @staticmethod
    def parse_index(response_text: str):
        c, i = response_text[:3].split('-')
        return ord(c) - 65, int(i) - 1

    @staticmethod
    def parse_bracket(response_text: str) -> list:
        result = []
        for i, c in enumerate(response_text[:-4]):
            if c == '[' and response_text[i + 4] == ']':
                result.append(response_text[i + 1:i + 4])
        return result

    @classmethod
    def add_new_question(cls, pre_messages: list, ai_response: str, new_question: str) -> list:
        """(Not inplace)"""
        return pre_messages + [{'role': 'model', 'parts': [ai_response]}] + cls.create_message(new_question)


LOGS = []


def generate_content(message, logs=False) -> str:
    while True:
        response = None
        try:
            response = MODEL.generate_content(
                message, generation_config=CONFIG, safety_settings=SAFETY_SETTINGS
            )
            reply = response.text
            if logs:  # True or False
                LOGS.append(message + [{'role': 'model', 'parts': [reply]}])
            return reply
        except GoogleAPIError as e:
            input('\33[31m' + f"{e}" + '\33[0m')
        except ValueError:
            input(response.prompt_feedback)


class Manager(dict):
    def __init__(self, data: dict, good_type=None):
        super().__init__(data)
        if good_type is not None:
            self['商品類型'] = good_type
        if 'GOODS' in self:
            self['GOODS_NUM'] = len(self['GOODS'])
            self['FEATURE_NUM'] = self['GOODS'][0]['商品特色'].count('\n') + 1
            assert self['FEATURE_NUM'] < 10, "String processing issues"
            self['INFO'] = []  # type: list[str]
            for i, d in enumerate(self['GOODS']):
                if 'TARGET' in d:
                    self['TARGET'] = d['TARGET']
                    self['PERSONA'] = d['PERSONA']
                char = chr(65 + i)
                features = d['商品特色'].split('\n')
                for j, feature in enumerate(features, 1):
                    self['INFO'].append(f"{char}-{j}：{feature}")
                self['INFO'].append(f"情境{char}：{d['PERSONA']}")
                self['INFO'].append('')  # sep

    def get_persona(self) -> str:
        question = PERSONA_PROMPT % self['商品類型'] + self['商品特色'].replace('\n', '\\n')
        print(self['商品特色'].replace('\n', '\\n'))
        message = Utils.create_message(question)
        return generate_content(message)

    def get_user_first_question(self) -> str:
        act_user_prompt = ACT_USER_PROMPT % (self['PERSONA'], self['商品類型'])
        message = Utils.add_new_question(
            Utils.create_message(ACT_USER_PROMPT % SAMPLE_PERSONA_AND_TYPE),
            SAMPLE_USER_QUESTION, act_user_prompt
        )
        return generate_content(message)

    def start_conversation(self, max_round=5) -> (list[str], int):
        conversation = []
        for d in self['GOODS']:
            if 'CONVERSATION' in d:
                self['TARGET'] = d['TARGET']
                conversation = d['CONVERSATION'].copy()
                break

        assistant_message = Utils.create_message(
            ASSISTANT_PROMPT % (self['GOODS_NUM'], self['商品類型'], self.info(with_goods_codes=True))
        )
        assistant_message = Utils.add_new_question(assistant_message, ASSISTANT_TASK_AGREE, conversation[0])

        target = self['TARGET'][1][:3]
        user_message = ACT_USER_PROMPT % (self['PERSONA'], self['商品類型']) + ACT_USER_INSTRUCTION % target[0]
        user_message = Utils.create_message(user_message)

        def user_sight(assistant_s: str):
            # replace code into feature
            for code in Utils.parse_bracket(assistant_s):
                if code[1] == '-':
                    good_idx, feature_idx = Utils.parse_index(code)
                    good_features = self['GOODS'][good_idx]['商品特色'].split('\n')
                    assistant_s = assistant_s.replace(f'[{code}]', f"「{good_features[feature_idx]}」")
            return assistant_s

        for _ in range(max_round * 2 - 1):
            is_assistant_turn = len(conversation) & 1
            if is_assistant_turn:
                s = generate_content(assistant_message, True)
                conversation.append(s)
                if target in Utils.parse_bracket(s):
                    return conversation, len(conversation) >> 1

                user_message = Utils.add_new_question(user_message, user_sight(conversation[-2]), user_sight(s))
            else:
                s = generate_content(user_message, True)
                conversation.append(s)
                assistant_message = Utils.add_new_question(assistant_message, conversation[-2], conversation[-1])
        return conversation, -1

    def choose_target(self):
        info = self.info(True)
        print(info)
        question = CHOOSE_TARGET_PROMPT % (self['GOODS_NUM'], self['FEATURE_NUM'], info)
        message = Utils.create_message(question)
        return generate_content(message)

    def info(self, with_persona=False, with_goods_codes=False) -> str:
        if with_persona:
            result = self['INFO']
        else:
            result = [s for i, s in enumerate(self['INFO']) if i % 5 != 3]
        if with_goods_codes:
            result[0] = "[商品A]\n" + result[0]
            for i, s in enumerate(result[:-1]):
                if not s:
                    result[i] = f"\n[商品{result[i + 1][0]}]"
        return '\n'.join(result)


def data_add_persona(source_dir=SOURCE_DIR, output_dir=GOODS_DIR):
    for source_json in os.listdir(source_dir):
        goods_type = stem_name(source_json).split('-')[1]
        groups = load_json(pj(source_dir, source_json))  # type: list[list[dict]]
        # add persona inplace
        for group in groups:
            for d in group:
                manager = Manager(d, goods_type)
                persona = manager.get_persona()
                print('\33[93m' + persona + '\33[0m')  # yellow
                d['PERSONA'] = persona
        dump_json(groups, pj(output_dir, source_json))


def data_add_target(goods_dir=GOODS_DIR, output_dir=TARGET_DIR, shuffle_func=None):
    if shuffle_func is None:
        def shuffle_func(lst: list):
            return lst
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    for goods_json in os.listdir(goods_dir):
        groups = load_json(pj(goods_dir, goods_json))  # type: list[list[dict]]
        for group in groups:
            shuffle_func(group)
            (target_good, feature_index), reason = Manager({'GOODS': group}).choose_target()
            group[target_good]['TARGET'] = feature_index, reason

        dump_json(groups, pj(output_dir, goods_json))


def data_get_first_question(target_dir=TARGET_DIR, output_dir=QUESTION_DIR):
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    for target_json in os.listdir(target_dir):
        goods_type = stem_name(target_json).split('-')[1]
        groups = load_json(pj(target_dir, target_json))  # type: list[list[dict]]
        for group in groups:
            for d in group:
                if 'TARGET' in d:
                    manager = Manager(d, goods_type)
                    question = manager.get_user_first_question()
                    print(question)
                    d['CONVERSATION'] = [question]

        dump_json(groups, pj(output_dir, target_json))


def data_start_conversation(question_dir=QUESTION_DIR, output_dir=CONVERSATION_DIR):
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    for target_json in os.listdir(question_dir):
        goods_type = stem_name(target_json).split('-')[1]
        groups = load_json(pj(question_dir, target_json))  # type: list[dict]
        for group in groups:
            manager = Manager({'GOODS': group}, goods_type)
            conv, rd = manager.start_conversation()

            Utils.print_message(LOGS[-1])
            LOGS.clear()

            target_idx = ord(manager['TARGET'][1][0]) - 65
            group[target_idx]['CONVERSATION'] = conv
            group[target_idx]['ROUND'] = rd
            print(manager['TARGET'][1][:3], rd, '#' * 30)

        dump_json(groups, pj(output_dir, target_json))


if __name__ == '__main__':
    data_add_persona()
    data_add_target()
    data_start_conversation()
