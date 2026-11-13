"""Word of the year: the word you typed in the most messages, minus filler words.

Each word counts once per message, so one pasted log cannot win. Code blocks, quotes,
links, paths, numbers and words shorter than four letters are ignored, and so are the
politeness and swear words (they have their own card).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Optional

STOPWORDS: set[str] = set(str("""
about above after again against also always another anything around because been before being below
between both cannot could does doing done down during each else even every from further have having here
hers herself himself into itself just last like make many maybe more most much must myself need never
next only other ours ourselves over same shall should since some still such than that their theirs them
themselves then there these they thing things this those though through under until very want were what
when where which while will with within without would your yours yourself yourselves okay yeah sure
also really right well good just going know think thats dont doesnt didnt cant wont isnt arent its
please thanks thank sorry could would should let lets used using use first second new now get got
make made take took see look looking give show tell said says check able sure yes nope
aber alle allem allen aller alles also andere anderen anderer anderes auch dann darf darum dass daher
damit dabei dadurch dafür dagegen daran darauf daraus darin darüber davon dazu dein deine deinem deinen
deiner denn dessen deshalb diese diesem diesen dieser dieses doch dort durch eben eher eine einem einen
einer eines einfach einmal etwas euch euer eure falls ganz gerade gibt gleich habe haben hast hatte
hätte hier hinter immer ihnen ihre ihrem ihren ihrer ihres jede jedem jeden jeder jedes jetzt kann
kannst keine keinem keinen keiner können könnte machen macht mach mehr mein meine meinem meinen meiner
mich mir mit muss musst müssen nach nicht nichts noch nochmal oben oder ohne schon sehr sein seine
seinem seinen seiner selbst sich sind soll sollen sollte sondern sonst über unter viel viele vielleicht
voll vom von vor wann warum was weil weiter welche welchem welchen welcher wenn werde werden wieder
will wird wirklich wurde würde zwar zwischen alles gut okay danke bitte bitten wäre wären geht gehen
mach machst sagen sage sagt schau schauen schreib schreibe lass lasse lassen nimm nehmen gibt geben
jetzt heute morgen gestern hallo hier dies diese neue neuen neues erst erstmal also genau dazu
para pero como todo esta este esto estos estas tiene tengo puedes puede hacer donde cuando porque
pour avec dans mais sont cette tout tous faire peux peut plus moins aussi comme
""").split())

_WORD = re.compile(r"[^\W\d_]{4,24}", re.U)
_LINKISH = ("/", "\\", "@", "www.", "=", "_")


def words_in(text: str) -> set[str]:
    """Distinct candidate words of one cleaned user message. Tokens that look like links,
    paths, mail addresses, identifiers or key=value pairs are dropped whole (linear, no regex
    backtracking on long tokens)."""
    keep = [tok for tok in text.split() if not any(c in tok for c in _LINKISH)]
    return {w.lower() for w in _WORD.findall(" ".join(keep))}


def parse_renames(items: Iterable[str]) -> dict[str, str]:
    """["acme=Northstar", "globex = Client B"] -> {"acme": "Northstar", "globex": "Client B"}."""
    out: dict[str, str] = {}
    for item in items or ():
        old, sep, new = str(item).partition("=")
        if sep and old.strip() and new.strip():
            out[old.strip().lower()] = new.strip()
    return out


class WordCounter:
    def __init__(self, exclude: Iterable[str] = (), skip: Iterable[str] = (), skip_fn=None,
                 rename: Optional[dict] = None):
        self.counts: Counter = Counter()
        # Shown under another name, e.g. a client name replaced by a code name. Keys are lower case.
        self.rename: dict[str, str] = {str(k).lower(): str(v) for k, v in (rename or {}).items() if str(v).strip()}
        for new in list(self.rename.values()):  # the code name typed in lower case is the same word
            self.rename.setdefault(new.lower(), new)
        self.skip_fn = skip_fn  # extra filter, e.g. swear words (they have their own card)
        self._checked: dict[str, bool] = {}
        self.skip: set[str] = set(STOPWORDS)
        for w in list(exclude) + list(skip):
            for part in str(w).lower().split():
                self.skip.add(part)

    def add(self, text: str) -> None:
        seen: set[str] = set()
        for w in words_in(text):
            w = self.rename.get(w, w)
            if w in seen:  # a word and its new name in one message count once
                continue
            seen.add(w)
            if w.lower() in self.skip and w not in self.rename.values():
                continue
            if self.skip_fn is not None:
                bad = self._checked.get(w)
                if bad is None:
                    bad = self._checked[w] = bool(self.skip_fn(w))
                if bad:
                    continue
            self.counts[w] += 1

    def top(self, n: int = 5) -> list[tuple[str, int]]:
        """Most messages first; ties alphabetically, so the result does not depend on hash order."""
        return sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
