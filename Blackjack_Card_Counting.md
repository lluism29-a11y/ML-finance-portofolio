**Author: Lluis Marill**

# Card Counting in Blackjack: A Monte Carlo Study

In this notebook I use my blackjack simulator ([`blackjack_sim.py`](blackjack_sim.py)) to study whether card counting can overcome the house edge in a game with unfavourable rules, and how much risk comes with it.

**The game.** Two decks, dealer stands on soft 17, double after split allowed, no surrender, 75% penetration, and, crucially, **blackjack pays 6:5** instead of the usual 3:2. The 6:5 payout alone costs the player about 1.4% per hand, so this is a game where a basic-strategy player is expected to lose.

**The strategies.** Both players use basic strategy for every playing decision; they only differ in how much they bet:
1. **Flat betting**: always bet 1 unit.
2. **Hi-Lo counting with a steep ramp**: keep the Hi-Lo running count (+1 for 2–6, −1 for tens and aces), convert it to the true count $\mathrm{TC} = \text{running count} / \text{decks remaining}$, and bet
$$
\text{bet} = \max\big(1,\ 2(\lfloor \mathrm{TC} \rfloor - 1)\big) \text{ units}.
$$

**The experiment.** For each strategy I simulate **30 independent sessions of 10,000 rounds** and look at the bankroll paths, the expected bankroll with a confidence band, the distribution of final results, and confidence intervals for the edge.

Both strategies use the same seeds, so session $k$ of the counter sees exactly the same cards as session $k$ of the flat bettor. The only difference is the bet size, which makes the comparison paired and much sharper.

## 1. Setup

```
Rules: 2 decks, S17, DAS, no surrender, BJ pays 1.2:1, 75% penetration
```

## 2. Running the simulations

For every session I keep the bankroll path (sampled every few rounds) together with the summary statistics returned by the simulator.

```
Flat betting         done, final results: mean   -167.1 units
```

```
Hi-Lo, bet 2(TC-1)   done, final results: mean    -23.1 units
```

## 3. Bankroll paths

Each thin line is one session of 10,000 rounds. The thick line is the average over the 30 sessions, and the shaded area is a pointwise 95% confidence interval for the **expected** bankroll,
$$
\bar B_t \pm t_{29,\,0.975}\, \frac{s_t}{\sqrt{30}},
$$
where $\bar B_t$ and $s_t$ are the mean and standard deviation of the 30 bankrolls after $t$ rounds.

![Figure 1](figures/blackjack/figure_1.png)

Both strategies on one plot, to compare the drift (mean) and the spread of outcomes. Here the shaded areas show the range between the 5% and 95% empirical quantiles of the 30 sessions, i.e. where a typical single session ends up, rather than the uncertainty in the mean.

![Figure 2](figures/blackjack/figure_2.png)

## 4. Distribution of final results

![Figure 3](figures/blackjack/figure_3.png)

## 5. Confidence intervals for the edge

For each session I compute the **player edge** (net result divided by the total amount initially bet) and the **EV per round** in units. The 30 sessions are independent, so a $t$-interval over sessions gives a 95% confidence interval for each quantity. I also report the average bet, the worst drawdown, and the fraction of sessions that ended in profit.

|  | Flat betting | Hi-Lo, bet 2(TC-1) |
|---|---|---|
| Edge per unit bet | -1.67% | -0.12% |
| 95% CI (edge) | [-2.09%, -1.25%] | [-0.86%, +0.63%] |
| EV per round (units) | -0.0167 | -0.0023 |
| 95% CI (EV) | [-0.0209, -0.0125] | [-0.0199, +0.0152] |
| Average bet (units) | 1.00 | 2.39 |
| SD per round (units) | 1.13 | 4.80 |
| Mean worst drawdown | -208.4 | -410.3 |
| Sessions in profit | 3% | 57% |

Because session $k$ of both strategies uses the same cards, I can also look at the **paired difference** in final results. This removes most of the card-luck noise that both players share.

```
Counter minus flat bettor after 10,000 rounds: +144.0 units (95% CI -10.0 to +297.9)
Counter did better in 63% of the sessions
```

## 6. Where does the counter's edge come from?

The counter's advantage comes from betting more when the remaining cards are rich in tens and aces. The plot below shows how often each true count occurs in a shoe and what the counter bets there.

![Figure 4](figures/blackjack/figure_4.png)

```
Rounds at TC >= 2 (where the counter raises the bet): 22.7%
```

## 7. Conclusions

- **Flat betting clearly loses.** With 6:5 blackjack, the basic-strategy player has an edge of about −1.7% per unit bet, with a 95% confidence interval of roughly [−2.1%, −1.3%], entirely below zero. Only 1 of the 30 sessions ended in profit.
- **Counting with a steep ramp removes almost all of the house edge, but not more.** Betting $2(\mathrm{TC}-1)$ units brings the edge to about −0.1%, i.e. essentially break-even. The confidence interval, roughly [−0.9%, +0.6%], contains zero, so with this amount of data we cannot say whether the counter has a positive or a negative edge. The 6:5 payout is costly enough that a pure betting ramp barely compensates for it.
- **On the same cards, the counter does better.** The paired comparison shows the counter ending about 144 units ahead of the flat bettor on average (the 95% interval, roughly [−10, +298], only just includes zero), and beating the flat bettor in about 63% of the sessions.
- **The price is variance.** The counter's average bet is about 2.4 units, and the standard deviation per round is more than four times that of the flat bettor. The average worst drawdown roughly doubles, and individual sessions end far in the red or far in the black. This is why the confidence intervals for the counter are so much wider.

**Caveats and extensions.** The simulation assumes perfect counting and perfect basic strategy, an unlimited bankroll, and no table maximum. In a real casino a spread this steep would quickly attract attention. Natural extensions, all supported by the simulator, are true-count playing deviations (`deviations=True`), wonging (sitting out at negative counts), comparing with a 3:2 game, and running more sessions to tighten the confidence intervals.

---

The full code behind this report is in [`Blackjack_Card_Counting.ipynb`](Blackjack_Card_Counting.ipynb) and the simulator in [`blackjack_sim.py`](blackjack_sim.py).
