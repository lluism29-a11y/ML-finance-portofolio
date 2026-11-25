"""
Blackjack Monte Carlo simulator.

Plays many rounds of blackjack with a multi-deck shoe, using basic strategy
for the player, and reports the player's expected return (house edge),
variance, and a 95% confidence interval. Optional Hi-Lo card counting with
a bet spread shows how counting shifts the edge.

Usage examples:
    python blackjack_sim.py                       # 200k rounds, 6 decks, S17, DAS
    python blackjack_sim.py -n 1000000 --h17      # dealer hits soft 17
    python blackjack_sim.py --surrender --decks 8
    python blackjack_sim.py --count --spread 8    # Hi-Lo counting, 1-8 bet spread
    python blackjack_sim.py --count --deviations  # counting + true-count deviations
    python blackjack_sim.py --bet steep           # bet 2(TC-1) units
    python blackjack_sim.py --bet jump --wong     # 1 or 12 units, sit out at TC < -1
    python blackjack_sim.py --wong --wong-tc 1    # sit out while TC < +1
    python blackjack_sim.py --stop-below -100     # stop once down more than 100 units
    python blackjack_sim.py --bj-payout 1.2       # 6:5 blackjack
"""

import argparse
import math
import random
from dataclasses import dataclass

# Card values; 11 represents an ace. Four 10-valued ranks (10, J, Q, K).
RANKS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]


@dataclass
class Rules:
    decks: int = 6
    penetration: float = 0.75   # fraction of shoe dealt before reshuffle
    h17: bool = False           # dealer hits soft 17
    das: bool = True            # double after split allowed
    surrender: bool = False     # late surrender allowed
    max_hands: int = 4          # max hands after splitting
    bj_payout: float = 1.5      # 3:2 = 1.5, 6:5 = 1.2


# --------------------------------------------------------------------- shoe

def hilo(card):
    if card <= 6:
        return 1
    if card >= 10:
        return -1
    return 0


class Shoe:
    def __init__(self, rules, rng):
        self.rules = rules
        self.rng = rng
        self.shuffle()

    def shuffle(self):
        self.cards = RANKS * 4 * self.rules.decks
        self.rng.shuffle(self.cards)
        self.cut = int(len(self.cards) * (1 - self.rules.penetration))
        self.running_count = 0

    def draw(self, seen=True):
        card = self.cards.pop()
        if seen:
            self.running_count += hilo(card)
        return card

    def reveal(self, card):
        """Count a card that was dealt face down."""
        self.running_count += hilo(card)

    def needs_shuffle(self):
        return len(self.cards) <= self.cut

    def true_count(self):
        decks_left = max(len(self.cards) / 52, 0.5)
        return self.running_count / decks_left


# ------------------------------------------------------------ hand helpers

def hand_value(cards):
    """Return (total, is_soft)."""
    total = sum(cards)
    aces = cards.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards)[0] == 21


# ---------------------------------------------------------- basic strategy

def basic_strategy(cards, up, rules, can_double, can_split, can_surrender):
    """Return 'H' hit, 'S' stand, 'D' double, 'P' split, 'R' surrender."""
    total, soft = hand_value(cards)

    def double_or(fallback):
        return "D" if can_double else fallback

    # Pairs
    if can_split and len(cards) == 2 and cards[0] == cards[1]:
        p = cards[0]
        if p in (11, 8):
            return "P"
        if p == 9 and up in (2, 3, 4, 5, 6, 8, 9):
            return "P"
        if p == 7 and up <= 7:
            return "P"
        if rules.das:
            if p == 6 and up <= 6:
                return "P"
            if p == 4 and up in (5, 6):
                return "P"
            if p in (2, 3) and up <= 7:
                return "P"
        else:
            if p == 6 and 3 <= up <= 6:
                return "P"
            if p in (2, 3) and 4 <= up <= 7:
                return "P"

    # Late surrender (hard totals, first two cards only)
    if can_surrender and not soft:
        if total == 16 and up in (9, 10, 11):
            return "R"
        if total == 15 and up == 10:
            return "R"
        if rules.h17 and up == 11 and total in (15, 17):
            return "R"

    # Soft totals
    if soft:
        if total >= 20:
            return "S"
        if total == 19:
            return double_or("S") if (rules.h17 and up == 6) else "S"
        if total == 18:
            if 3 <= up <= 6 or (rules.h17 and up == 2):
                return double_or("S")
            return "S" if up in (2, 7, 8) else "H"
        if total == 17:
            return double_or("H") if 3 <= up <= 6 else "H"
        if total in (15, 16):
            return double_or("H") if 4 <= up <= 6 else "H"
        if total in (13, 14):
            return double_or("H") if up in (5, 6) else "H"
        return "H"

    # Hard totals
    if total >= 17:
        return "S"
    if total >= 13:
        return "S" if up <= 6 else "H"
    if total == 12:
        return "S" if 4 <= up <= 6 else "H"
    if total == 11:
        return double_or("H") if (up != 11 or rules.h17) else "H"
    if total == 10:
        return double_or("H") if up <= 9 else "H"
    if total == 9:
        return double_or("H") if 3 <= up <= 6 else "H"
    return "H"


# ------------------------------------------------- count-based deviations

# (hand, upcard, deviation, direction, threshold); an ace upcard is 11.
# hand is a hard total, or ("pair", rank) for a pair.
# "ge": deviate when TC >= threshold; "lt": deviate when TC < threshold.
DEVIATIONS = [
    (16, 10, "S", "ge", 0),
    (15, 10, "S", "ge", 4),
    (("pair", 10), 5, "P", "ge", 5),
    (("pair", 10), 6, "P", "ge", 4),
    (10, 10, "D", "ge", 4),
    (12, 3, "S", "ge", 2),
    (12, 2, "S", "ge", 3),
    (11, 11, "D", "ge", 1),
    (9, 2, "D", "ge", 1),
    (10, 11, "D", "ge", 4),
    (9, 7, "D", "ge", 3),
    (16, 9, "S", "ge", 5),
    (13, 2, "H", "lt", -1),
    (12, 4, "H", "lt", 0),
    (12, 5, "H", "lt", -2),
    (12, 6, "H", "lt", -1),
    (13, 3, "H", "lt", -2),
]
INSURANCE_TC = 3   # take insurance when TC >= +3


def deviate(cards, up, tc, action, can_double, can_split):
    """Return the deviation from basic strategy `action` at true count `tc`.

    Only hit/stand plays are overridden, so basic-strategy splits and
    surrenders are kept.
    """
    if action not in ("H", "S"):
        return action
    total, soft = hand_value(cards)
    is_pair = len(cards) == 2 and cards[0] == cards[1]
    for hand, dev_up, dev_action, direction, threshold in DEVIATIONS:
        if dev_up != up:
            continue
        if isinstance(hand, tuple):
            if not (is_pair and can_split and cards[0] == hand[1]):
                continue
        elif soft or total != hand:
            continue
        if dev_action == "D" and not can_double:
            continue
        if (tc >= threshold) if direction == "ge" else (tc < threshold):
            return dev_action
    return action


# --------------------------------------------------------------- one round

def play_round(shoe, rules, bet, deviations=False):
    """Play one round; return (net result in units, total amount wagered)."""
    player = [shoe.draw(), shoe.draw()]
    dealer = [shoe.draw(), shoe.draw(seen=False)]   # hole card is face down
    up = dealer[0]

    dealer_bj = is_blackjack(dealer)
    player_bj = is_blackjack(player)

    # Insurance is offered against an ace, before the dealer peeks
    insurance = 0.0
    if deviations and up == 11 and shoe.true_count() >= INSURANCE_TC:
        insurance = bet / 2
    ins_net = 2 * insurance if dealer_bj else -insurance

    # Dealer peeks for blackjack with an ace or ten showing
    if dealer_bj:
        shoe.reveal(dealer[1])
        return (0.0 if player_bj else -bet) + ins_net, bet + insurance
    if player_bj:
        shoe.reveal(dealer[1])
        return rules.bj_payout * bet + ins_net, bet + insurance

    hands = [{"cards": player, "bet": bet, "split_aces": False, "surrendered": False}]
    i = 0
    while i < len(hands):
        h = hands[i]
        if h["split_aces"]:
            i += 1
            continue
        first_decision = True
        while True:
            cards = h["cards"]
            total, _ = hand_value(cards)
            if total >= 21:
                break
            two_cards = len(cards) == 2
            is_split_hand = len(hands) > 1
            can_double = two_cards and (rules.das or not is_split_hand)
            can_split = (two_cards and cards[0] == cards[1]
                         and len(hands) < rules.max_hands)
            can_surr = (rules.surrender and first_decision
                        and not is_split_hand and two_cards)
            action = basic_strategy(cards, up, rules, can_double, can_split, can_surr)
            if deviations:
                action = deviate(cards, up, shoe.true_count(), action,
                                 can_double, can_split)
            first_decision = False

            if action == "S":
                break
            if action == "H":
                cards.append(shoe.draw())
            elif action == "D":
                h["bet"] *= 2
                cards.append(shoe.draw())
                break
            elif action == "R":
                h["surrendered"] = True
                break
            elif action == "P":
                pair = cards[0]
                new_hand = {"cards": [pair, shoe.draw()], "bet": h["bet"],
                            "split_aces": pair == 11, "surrendered": False}
                h["cards"] = [pair, shoe.draw()]
                if pair == 11:
                    h["split_aces"] = True   # split aces get one card each
                hands.append(new_hand)
                if pair == 11:
                    break
        i += 1

    wagered = sum(h["bet"] for h in hands) + insurance
    shoe.reveal(dealer[1])

    # Dealer plays only if some hand is still live
    live = [h for h in hands
            if not h["surrendered"] and hand_value(h["cards"])[0] <= 21]
    if live:
        while True:
            d_total, d_soft = hand_value(dealer)
            if d_total < 17 or (d_total == 17 and d_soft and rules.h17):
                dealer.append(shoe.draw())
            else:
                break
    d_total, _ = hand_value(dealer)

    net = ins_net
    for h in hands:
        p_total, _ = hand_value(h["cards"])
        if h["surrendered"]:
            net -= h["bet"] / 2
        elif p_total > 21:
            net -= h["bet"]
        elif d_total > 21 or p_total > d_total:
            net += h["bet"]
        elif p_total < d_total:
            net -= h["bet"]
    return net, wagered


# -------------------------------------------------------------- simulation

WONG_OUT_TC = -1   # default: with wonging, sit out while TC < -1
PATH_POINTS = 2000  # max points kept of the bankroll path


def bet_size(mode, tc, spread):
    """Initial bet in units for betting `mode` at (floored) true count `tc`."""
    if mode == "hilo":
        return float(max(1, min(spread, tc)))
    if mode == "steep":
        return float(max(1, 2 * (tc - 1)))
    if mode == "jump":
        return 12.0 if tc >= 2 else 1.0
    return 1.0


def simulate(n_rounds, rules, mode="flat", spread=8, deviations=False,
             wong=False, wong_tc=WONG_OUT_TC, stop_below=None, seed=None,
             on_progress=None):
    # on_progress(round, bankroll, worst_bankroll) is called at every point of
    # the bankroll path, so a caller can show the simulation live.
    rng = random.Random(seed)
    shoe = Shoe(rules, rng)

    total_net = 0.0
    total_sq = 0.0
    total_initial = 0.0
    total_wagered = 0.0
    sat_out = 0
    worst_bankroll = 0.0   # lowest running net result; 0 if never below start
    outcomes = {"win": 0, "loss": 0, "push": 0}

    # Running net result, sampled to at most ~PATH_POINTS points for plotting
    step = max(1, n_rounds // PATH_POINTS)
    bankroll_path = [(0, 0.0)]
    stopped_at = None   # round at which the bankroll fell below stop_below

    for i in range(1, n_rounds + 1):
        if shoe.needs_shuffle():
            shoe.shuffle()

        tc = math.floor(shoe.true_count())
        if wong and tc < wong_tc:
            # Sit out: the round is still dealt, so the cards leave the shoe
            play_round(shoe, rules, 0.0, deviations)
            sat_out += 1
        else:
            bet = bet_size(mode, tc, spread)

            net, wagered = play_round(shoe, rules, bet, deviations)
            total_net += net
            worst_bankroll = min(worst_bankroll, total_net)
            total_sq += net * net
            total_initial += bet
            total_wagered += wagered
            if net > 0:
                outcomes["win"] += 1
            elif net < 0:
                outcomes["loss"] += 1
            else:
                outcomes["push"] += 1

        if stop_below is not None and total_net < stop_below:
            stopped_at = i
            bankroll_path.append((i, total_net))
            if on_progress:
                on_progress(i, total_net, worst_bankroll)
            break

        if i % step == 0 or i == n_rounds:
            bankroll_path.append((i, total_net))
            if on_progress:
                on_progress(i, total_net, worst_bankroll)

    played = (stopped_at or n_rounds) - sat_out
    if played == 0:
        raise SystemExit("Sat out every round; nothing was played.")
    mean = total_net / played
    var = total_sq / played - mean ** 2
    sd = math.sqrt(var)
    se = sd / math.sqrt(played)
    return {
        "rounds": played,
        "sat_out": sat_out,
        "stopped_at": stopped_at,
        "net": total_net,
        "worst_bankroll": worst_bankroll,
        "bankroll_path": bankroll_path,
        "mean_per_round": mean,
        "sd_per_round": sd,
        "ci95": (mean - 1.96 * se, mean + 1.96 * se),
        "return_per_initial_bet": total_net / total_initial,
        "avg_bet": total_initial / played,
        "total_wagered": total_wagered,
        "outcomes": outcomes,
    }


def describe(rules, mode, spread, deviations, wong, wong_tc=WONG_OUT_TC,
             stop_below=None):
    parts = [f"{rules.decks} decks",
             "H17" if rules.h17 else "S17",
             "DAS" if rules.das else "no DAS",
             "late surrender" if rules.surrender else "no surrender",
             f"BJ pays {rules.bj_payout:g}:1",
             f"{rules.penetration:.0%} penetration"]
    if mode == "hilo":
        parts.append(f"Hi-Lo count, 1-{spread} spread")
    elif mode == "steep":
        parts.append("steep ramp, bet 2(TC-1)")
    elif mode == "jump":
        parts.append("jump, 12 units at TC >= +2")
    else:
        parts.append("flat betting")
    parts.append("count deviations" if deviations else "basic strategy only")
    if wong:
        parts.append(f"wong out at TC < {wong_tc:+d}")
    if stop_below is not None:
        parts.append(f"stop below {stop_below:+g} units")
    return ", ".join(parts)


def main():
    ap = argparse.ArgumentParser(description="Blackjack Monte Carlo simulator")
    ap.add_argument("-n", "--rounds", type=int, default=500000)
    ap.add_argument("--decks", type=int, default=6)
    ap.add_argument("--penetration", type=float, default=0.75)
    ap.add_argument("--h17", action="store_true", help="dealer hits soft 17")
    ap.add_argument("--no-das", action="store_true", help="no double after split")
    ap.add_argument("--surrender", action="store_true", help="allow late surrender")
    ap.add_argument("--bj-payout", type=float, default=1.5)
    ap.add_argument("--bet", choices=["flat", "hilo", "steep", "jump"], default="flat",
                    help="betting mode: flat; hilo (bet TC, capped at --spread); "
                         "steep (bet 2(TC-1)); jump (12 units at TC >= +2, else 1)")
    ap.add_argument("--count", action="store_true", help="same as --bet hilo")
    ap.add_argument("--spread", type=int, default=8, help="max bet in units for --bet hilo")
    ap.add_argument("--wong", action="store_true",
                    help="sit out rounds while TC < --wong-tc")
    ap.add_argument("--wong-tc", type=int, default=WONG_OUT_TC,
                    help=f"with --wong, sit out while TC is below this (default {WONG_OUT_TC})")
    ap.add_argument("--stop-below", type=float, default=None,
                    help="stop the simulation once the bankroll falls below this many units "
                         "(e.g. -100)")
    ap.add_argument("--deviations", action="store_true",
                    help="deviate from basic strategy (and take insurance) by Hi-Lo true count")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rules = Rules(decks=args.decks, penetration=args.penetration, h17=args.h17,
                  das=not args.no_das, surrender=args.surrender,
                  bj_payout=args.bj_payout)

    mode = "hilo" if args.count else args.bet

    label = describe(rules, mode, args.spread, args.deviations, args.wong, args.wong_tc,
                     args.stop_below)
    print(f"Rules: {label}")
    print(f"Simulating {args.rounds:,} rounds...\n")
    r = simulate(args.rounds, rules, mode=mode, spread=args.spread,
                 deviations=args.deviations, wong=args.wong,
                 wong_tc=args.wong_tc, stop_below=args.stop_below, seed=args.seed)

    o = r["outcomes"]
    n = r["rounds"]
    lo, hi = r["ci95"]
    if r["stopped_at"]:
        print(f"Stopped at round {r['stopped_at']:,}: bankroll fell below {args.stop_below:+g} units")
    if args.wong:
        print(f"Rounds played:         {n:,}  (sat out {r['sat_out']:,})")
    print(f"Net result:            {r['net']:+,.1f} units")
    print(f"Worst bankroll:        {r['worst_bankroll']:+,.1f} units")
    print(f"Average bet:           {r['avg_bet']:.3f} units")
    print(f"EV per round:          {r['mean_per_round']:+.4f} units  "
          f"(95% CI {lo:+.4f} to {hi:+.4f})")
    print(f"Std dev per round:     {r['sd_per_round']:.3f} units")
    print(f"Player edge per unit bet: {r['return_per_initial_bet']:+.3%}")
    print(f"Win / loss / push:     {o['win']/n:.1%} / {o['loss']/n:.1%} / {o['push']/n:.1%}")


if __name__ == "__main__":
    main()