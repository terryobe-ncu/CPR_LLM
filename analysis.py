import os
import glob
from gemini import load_json, Utils
import gemini
from collections import Counter

TARGET_DIR = gemini.TARGET_DIR
CONVERSATION_DIR = gemini.CONVERSATION_DIR


def target_statistic(target_dir=TARGET_DIR):
    stack = []
    for json_path in glob.glob(target_dir + '/*'):
        groups = load_json(json_path)
        for group in groups:
            for d in group:
                if 'TARGET' in d:
                    stack.append(d['TARGET'][1][:3])

    s = ''.join(stack)
    print(s.count('-'))
    assert s.count('-') == len(os.listdir(target_dir)) * 10
    for c in 'ABCDE123':
        print(c + ':', s.count(c))


def inspect_features_and_personas(target_dir=TARGET_DIR):
    """Inspect for keywords in features and personas."""
    features_stack, targets_stack = [], []
    for json_path in glob.glob(target_dir + '/*'):
        groups = load_json(json_path)
        for group in groups:
            for d in group:
                features_stack.append(d['商品特色'])
                if 'TARGET' in d:
                    targets_stack.append(d['TARGET'][1][:3])

    features_string = '\n'.join(features_stack)
    targets_string = '\n'.join(targets_stack)
    print(features_string.count('momo'))  # Advertising contents of the platform
    print(targets_string.count('momo'))  # Expected 0, platform name should not exist in targets
    print(features_string.count('MOMO'))  # Advertising contents of the platform
    print(targets_string.count('MOMO'))  # Expected 0, platform name should not exist in targets


def test_target_position_bias(r_target_dir='data/r_target'):
    """
    Gemini’s choice will have position bias, the proportion of choosing A and C is higher.
    This function will reverse the goods order for each group, and then generate the new target data
    and show the statistic result of it.
    """

    def reverse_fuc(lst: list):
        lst.reverse()

    gemini.data_add_target(output_dir=r_target_dir, shuffle_func=reverse_fuc)
    target_statistic(r_target_dir)


def count_conversation_round(conversation_dir=CONVERSATION_DIR):
    counter = Counter()
    two_round = [0, 0]  # wrong product, correct product
    for json_path in glob.glob(conversation_dir + '/*'):
        groups = load_json(json_path)
        for group in groups:
            for d in group:
                if 'ROUND' in d:
                    counter[d['ROUND']] += 1
                    if d['ROUND'] == 2:
                        target_good = d['TARGET'][1][0]
                        two_round['[' + target_good in d['CONVERSATION'][1]] += 1

    sm = sum(counter.values())
    for k in sorted(counter):
        print(k, counter[k], '%.2f%%' % (counter[k] / sm * 100))

    print(two_round)


def count_number_of_features_of_first_assistant_reply(conversation_dir=CONVERSATION_DIR):
    counter = Counter()
    sm = 0
    for json_path in glob.glob(conversation_dir + '/*'):
        groups = load_json(json_path)
        for group in groups:
            for d in group:
                if 'CONVERSATION' in d:
                    sm += 1
                    features = filter(lambda s: s[1] == '-', Utils.parse_bracket(d['CONVERSATION'][1]))
                    counter[len(frozenset(features))] += 1

    for k in sorted(counter):
        print(k, counter[k], '%.2f%%' % (counter[k] / sm * 100))


if __name__ == '__main__':
    target_statistic()
    # test_target_position_bias()
    # inspect_features_and_personas()
    # count_number_of_features_of_first_assistant_reply()
