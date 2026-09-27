"""A small profanity filter for text other badges send (BLAT chat).

    profanity.clean("what the 5h1t")  ->  "what the s***"

Matching is per word, case-insensitive, and sees through common swaps
(0->o, 1->i, 3->e, 4->a, 5->s, 7->t, @->a, $->s, !->i). A matched word keeps
its first letter and the rest become asterisks. Short roots only match a whole
word or the start of one, so "class", "Scunthorpe" and "cocktail"-style words
are not caught by accident; distinctive roots match anywhere in a word.

The word list is stored ROT13-encoded so this public source is not a plain
list of slurs. Each entry is a root, prefixed "=" for whole words only, "^"
for the start of a word, or nothing for anywhere in a word. It is a filter
for casual chat, not a guarantee: determined spelling will get through.
"""

_WORDS = ("shpx fuvg ovgpu ^phag avtt snttbg =snt =qvpx =qvpxf qvpxurnq =pbpx "
          "=pbpxf pbpxfhpx =nff nffubyr juber "
          "fyhg =phz chffl ^ergneq =gjng =gvg =gvgf onfgneq jnax wvmm ^cvff qvyqb "
          "^cbea xvxr =fcvp =puvax =qlxr genaal =ubr =ubrf ^obare")

_SWAPS = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t",
          "@": "a", "$": "s", "!": "i"}

_rules = None   # [(mode, root)], decoded on first use


def _rot13(s):
    out = []
    for c in s:
        o = ord(c)
        if 97 <= o <= 122:
            c = chr((o - 97 + 13) % 26 + 97)
        out.append(c)
    return "".join(out)


def _load():
    global _rules
    if _rules is None:
        _rules = []
        for entry in _WORDS.split():
            mode = entry[0] if entry[0] in "=^" else ""
            _rules.append((mode, _rot13(entry[len(mode):])))
    return _rules


def _is_bad(word):
    for mode, root in _load():
        if mode == "=":
            if word == root:
                return True
        elif mode == "^":
            if word.startswith(root):
                return True
        elif root in word:
            return True
    return False


def clean(text: str) -> str:
    """`text` with profane words masked. Same length as `text`."""
    norm = "".join(_SWAPS.get(c, c) for c in text.lower())
    out = list(text)
    i, n = 0, len(norm)
    while i < n:
        if not ("a" <= norm[i] <= "z"):
            i += 1
            continue
        j = i
        while j < n and "a" <= norm[j] <= "z":
            j += 1
        if _is_bad(norm[i:j]):
            for k in range(i + 1, j):
                out[k] = "*"
        i = j
    return "".join(out)
