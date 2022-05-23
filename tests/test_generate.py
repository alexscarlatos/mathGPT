import torch

from generate import infer_math_pos
from constants import TokenType

def test_infer_math_pos():
    # Cases:
    # 1 - OP leads to child
    # 2 - VAR leads to sibling
    # 3 - NUM leads to sibling
    # 4 - END leads to parent's sibling
    # 5 - VAR ends the formula
    # 6 - END ends the formula
    prev_pos_vecs = torch.LongTensor([
        [0, 0, 0],
        [0, 1, 0],
        [0, 3, 1],
        [0, 5, 3],
        [0, 0, 0],
        [0, 2, 0],
    ])
    prev_pos_levels = torch.LongTensor([
        0,
        1,
        2,
        2,
        0,
        1,
    ])
    prev_token_types = torch.LongTensor([
        TokenType.OP,
        TokenType.VAR,
        TokenType.NUM,
        TokenType.END,
        TokenType.VAR,
        TokenType.END,
    ])

    new_pos_vecs, new_pos_levels = infer_math_pos(prev_pos_vecs, prev_pos_levels, prev_token_types)
    assert torch.all(new_pos_vecs == torch.LongTensor([
        [0, 0, 0],
        [0, 2, 0],
        [0, 3, 2],
        [0, 6, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]))
    assert torch.all(new_pos_levels == torch.LongTensor([
        1,
        1,
        2,
        1,
        0,
        0,
    ]))

def test_generate():
    pass # TODO: mock model, only need to generate one new token (until we have new techniques)

def test_predictions():
    return # TODO
    type_to_token_probs = {
        TokenType.TEXT: torch.Tensor([
            [[0.1, 0.2, 0.1], [0.4, 0.2, 0.1]],
            [[0.0, 0.0, 0.0], [0.5, 0.1, 0.1]]
        ]),
        TokenType.START_FORMULA: torch.Tensor([
            [[0.1], [0.4]],
            [[0.0], [0.5]]
        ]),
        TokenType.END_FORMULA: torch.Tensor([
            [[0.1], [0.4]],
            [[0.0], [0.5]]
        ]),
        TokenType.OP: torch.Tensor([
            [[0.1, 0.2, 0.1], [0.4, 0.2, 0.1]],
            [[0.0, 0.0, 0.0], [0.5, 0.1, 0.1]]
        ]),
        TokenType.NUM: torch.Tensor([
            [[0.1, 0.2, 0.1], [0.4, 0.2, 0.1]],
            [[0.0, 0.0, 0.0], [0.5, 0.1, 0.1]]
        ]),
        TokenType.VAR: torch.Tensor([
            [[0.1, 0.2, 0.1], [0.4, 0.2, 0.1]],
            [[0.0, 0.0, 0.0], [0.5, 0.1, 0.1]]
        ])
    }
    type_preds, token_preds = get_most_likely_predictions(type_to_token_probs)
    assert all(type_preds == [])
    assert all(token_preds == [])

