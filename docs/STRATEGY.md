# Strategy and operating plan (October 2026)

The evidence behind this is in [`MARKET.md`](MARKET.md). Everything here is a hypothesis until a buyer confirms it. No customer has been interviewed yet.

## The bet

**VirtuLab turns each pull request into a record of security testing that a firmware team can keep for its Cyber Resilience Act technical file.**

- **First customer:** a European industrial or connected-device company with roughly 5 to 50 firmware engineers, no in-house security lab, and products on sale in the EU. The likely champion is the firmware lead. The budget may sit with quality, compliance or the CTO.
- **Why now:** most CRA obligations apply from 11 December 2027, and the record is only useful if it builds up before then.
- **Why us:** we run the firmware on each change and report the exact line. Binary scanners work on finished images, and labs come once.
- **Second market:** medical devices. **Not now:** automotive, which also tends to want MC/DC and qualified tools.

## Proof so far

| Claim | Evidence | Strength |
| :-- | :-- | :-- |
| Finds defects in code we did not write | Three widely used open-source parsers, real undefined behaviour in each, in under 90,000 runs | Medium. Low severity, and not yet confirmed by maintainers |
| Finds fault-injection holes | Found real holes in our own hardened PIN code | Medium. Our own demo code |
| Setup is quick on outside code | A parser harness took minutes to write | Weak. Written by the author |
| Teams will pay | None | **None** |
| Assessors value the output | None | **None** |

Fuzzing found no memory corruption in those projects, so the honest line is "real defects, in seconds", not "critical vulnerabilities".

## Business weaknesses, ranked

| # | Weakness | Why it matters | What would fix it |
| :-- | :-- | :-- | :-- |
| 1 | **No customer contact at all** | Everything else is theory | 10 discovery calls ([`DISCOVERY.md`](DISCOVERY.md)) |
| 2 | **Licence just added** | Apache-2.0 is in the working tree, but counts only once committed and pushed | Push it before any outreach |
| 3 | **Who pays is unclear** | Engineers adopt, compliance may fund it. Different pitch and price | Ask in every call, and find one real budget line |
| 4 | **Thin moat** | The engine is QEMU, Renode, libFuzzer and GDB, all open. Sensor models are copyable | Build what compounds: evidence history, probe libraries, and customer integrations |
| 5 | **Works on few real targets** | Fault injection needs a QEMU board, and most real firmware needs peripherals those boards lack | Add Renode fault injection, or fault-inject host-testable logic. Test one real product first |
| 6 | **Finding value needs expert effort** | Harnesses and probes need security thinking. That can make this a services business | Probe templates for common patterns, starting with secure boot and PIN checks |
| 7 | **Demand for outside review may be small** | Secondary sources say default-class products self-assess. Then no assessor asks for our record, and the need is softer | Check the product class of each prospect. Class I and II may be the sharper target |
| 8 | **Standards are unsettled** | Secondary sources say the CRA harmonised standards are not all published | No standard-mapping claims until the text is read. Keep "evidence", drop "compliance" |
| 9 | **Hosted plan may clash with the buyer** | Regulated teams may refuse to upload firmware | Lead with on-premises. Test this in calls before building any hosted product |
| 10 | **Credibility** | A safety buyer asks who stands behind the tool. No company page, security policy or track record is visible | Working site and contact, security policy, published findings, an advisor from the field |
| 11 | **No distribution** | No audience yet | Maintainer-confirmed findings as technical posts, then r/embedded, Interrupt, Embedded World |
| 12 | **Well-funded neighbours** | ONEKEY offers free analysis, Code Intelligence sells fuzzing, eShard counts Thales as a customer | Partner with scanners. Stay narrow: per-PR, source-line, firmware-specific |
| 13 | **Name risk** | "The Virtulab" is a UK engineering company, and VirtusLab is a software firm. The EU trademark register blocked automated search, and a web search found nothing, which proves little | Search TMview and USPTO by hand, then ask a trademark lawyer before spending on the brand |
| 14 | **Website down** | virtulab.io redirects to HTTPS, which fails, so the README now points to GitHub issues. The domain has mail records, but its owner is not confirmed here | Fix the HTTPS certificate or hosting, then restore the site link |
| 15 | **Product proof gaps** | CI has never run on GitHub, own-build mode has only seen small projects, and fault sweeps sometimes stall and fail | Run the PR; try one real CMake project; fix the stall before a pilot |
| 16 | **Founder capacity** | Tool, models, sales and compliance knowledge are a lot for one person | Keep scope to this page, and stop adding sensors |

## Offer to test

**Pilot:** two weeks on one parser and one security check in the customer's real code, ending in an evidence record and a findings review. A fixed fee tests willingness to pay better than a free trial does.

| Tier | For | Price idea |
| :-- | :-- | :-- |
| Open source | Engineers trying it | Free |
| Team | On-premises evidence history and support | Test €1,000 to €3,000 per month |
| Pilot | First customers | Test €5,000 to €15,000 fixed |

These prices are guesses to test, not findings. One comparison site lists Memfault's Growth tier from $3,495 a month, and Wokwi's paid plans start in single digits, so the range is wide.

**Possible exit:** Nordic Semiconductor bought Memfault for a reported $120M in 2025, which suggests chip vendors buy firmware tooling.

## 90-day plan

| When | Goal | Done when |
| :-- | :-- | :-- |
| Week 1 | Remove blockers | Licence chosen, site or contact fixed, trademark checked, CI green on a real PR |
| Weeks 1 to 2 | Tell maintainers | Three reports sent, responses recorded |
| Weeks 2 to 6 | Learn | 10 discovery calls and 1 conformity assessor |
| Weeks 3 to 6 | First public proof | One post, after maintainers respond, on what was found and how |
| Weeks 6 to 10 | First pilot | One signed pilot on real code |
| Weeks 10 to 13 | Decide | See the stop rules below |

## Stop rules

Change the plan, rather than keep building, if by day 90:

- fewer than 3 of 10 teams describe this as a funded problem
- nobody will pay for a pilot
- a pilot cannot produce a useful result on real firmware within two weeks
- assessors say emulated evidence has no value

## Not doing now

More sensors, more boards, replacing vendor IDEs, a hosted product, or compliance claims.
