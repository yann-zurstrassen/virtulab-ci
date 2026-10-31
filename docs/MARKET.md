# Market notes (October 2026)

A working note for deciding what to build next. Sources are at the end. Most are vendor or law-firm summaries, not the regulations or standards themselves, and no customer has been interviewed. Nothing here is legal advice, and no market size is claimed because no reliable figure was found.

## What is pulling the market

| Pressure | What is known | Why it matters here |
| :-- | :-- | :-- |
| **EU Cyber Resilience Act** | Reporting of exploited vulnerabilities and severe incidents started on 11 September 2026. Most other requirements apply from 11 December 2027. Penalties for reporting breaches can reach €15 million or 2.5% of turnover | A fixed deadline for anyone selling connected products in the EU, with about 13 months left to build evidence habits. Harmonised standards are still being finished, so no source found yet says exactly which tests satisfy it |
| **FDA section 524B** | SBOM, vulnerability plan and disclosure are statutory for cyber devices. Penetration and fuzz testing are reported as guidance-level expectations scaled to risk. Secondary sources disagree on the current guidance date | Medical teams need test records tied to a threat model |
| **IEC 62443-4-1** | Secondary sources say section 9.4 covers fuzz and vulnerability testing, and that findings should be tracked | Industrial buyers ask for this in supplier contracts. Modbus and similar parsers are a natural target |
| **ISO/SAE 21434** | Reported to recommend fuzz testing. Not law, but often contractual | Automotive suppliers inherit it from customers |

## Who else is here

| Group | Examples | What they do | Gap we can use |
| :-- | :-- | :-- | :-- |
| Binary and supply-chain analysis | Finite State, Exein, Eclypsium | Analyse the finished image, SBOM, compliance | Runs after the build. We run the firmware on each PR. Partner rather than compete |
| Simulation for developers | Wokwi, Renode, QEMU | Run firmware without a board | Wokwi CI charges by minutes. They sell convenience, not evidence |
| Fuzzing for code | Code Intelligence, Black Duck | Fuzzing with compliance messaging | Keysight notes most fuzzers do not take the target hardware into account |
| Fault injection in software | eShard esFirmware, FiSim | Emulated fault campaigns on binaries | The closest match to our sharpest feature. esFirmware claims CI use, so this is the competitor to study first |
| Test labs | Keysight, CEA-Leti, Riscure | Experts and physical benches | Periodic and expensive. We make the checks routine, and labs stay the final gate |

## Our strengths, honestly

1. **Fault injection on every PR, down to a source line.** This is the rarest thing we do. It found real holes in our own "hardened" code during this work.
2. **Traceable models.** Every sensor row cites a document, revision and page, with its hash, and vendor code runs against the SHT31 model.
3. **Honest limits in every output.** The evidence record says what each check does not show, which is what an assessor needs.
4. **Trying it is cheap.** One file, one command, no hardware.

## Where to aim

**Lead with: the CRA-readiness evidence trail for small and mid-size firmware teams** in industrial products, which have a deadline and usually no security lab. Medical is the second market. Automotive comes later, because it wants qualified tools and MC/DC.

Possible split: the engine stays open, and paid plans cover hosted history of evidence across releases, audit exports and advanced fault models.

## Added after a second pass

- **Self-assessment:** secondary sources say default-class products can self-assess, class I can do so only with harmonised standards or similar, and class II and critical products need a notified body. Sources disagree on details, so check the regulation. It decides who actually reads our evidence.
- **Standards:** EN 18031 is harmonised under the Radio Equipment Directive. Sources describe it as a candidate for the CRA, not yet listed for it.
- **Comparable deals:** Nordic Semiconductor bought Memfault for a reported $120M in 2025. Code Intelligence raised a reported $12M Series A in 2022. eShard names Thales as an esFirmware customer.
- **Open-source business model:** Renode is MIT-licensed, and Antmicro sells support and engineering around it. That is a working model for the services side, and a warning about how thin the engine moat is.
- **Pricing signals:** ONEKEY sells tailored subscriptions and offers a free firmware analysis. CI Fuzz is sales-led for C/C++ enterprise use. One review site lists Memfault's Growth tier from $3,495 a month.

## Biggest risks

- **Unproven demand.** No buyer has confirmed they would pay. This is a hypothesis until 3 to 5 conversations happen.
- **Unproven on real firmware.** Nothing has run on a real customer build yet.
- **Standards could disappoint.** An assessor may not accept emulated evidence, and that is unknown until one is asked.
- **Platform reach.** QEMU fault injection covers few boards, and most real firmware needs peripherals that are not emulated.

## Sources

- [Goodwin on CRA obligations](https://www.goodwinlaw.com/en/insights/publications/2026/09/alerts-lifesciences-technology-preparing-for-eu-cyber-resilience-act)
- [Jones Day on CRA reporting](https://www.jonesday.com/de/insights/2026/07/eu-cyber-resilience-act-24hour-reporting-duties-start-september-11-2026)
- [ETSI CRA standards progress](https://erp.today/eu-cyber-resilience-act-etsi-advances-17-standards-as-reporting-deadline-nears/)
- [Finite State CRA timeline](https://finitestate.io/blog/cyber-resilience-act-timeline-2026-2027)
- [Black Duck on section 524B](https://blackduck.com/blog/understanding-fda-section-524b-medical-device-cybersecurity.html)
- [Black Duck on IEC 62443-4-1](https://www.blackduck.com/blog/software-testing-included-in-final-isa-iec-62443-4-1.html)
- [Automotive IQ on ISO 21434](https://www.automotive-iq.com/functional-safety/whitepapers/how-fuzzing-helps-comply-with-iso-21434)
- [Keysight on embedded fuzzing](https://www.keysight.com/jp/ja/products/services/device-vulnerability-analysis-services/security-evaluation/embedded-code-and-design-review.html)
- [Wokwi CI](https://wokwi.com/ci)
- [eShard esFirmware](https://www.eshard.com/esfirmware)
- [FiSim at Black Hat Europe 2018](https://infocondb.org/con/black-hat/black-hat-europe-2018/secure-boot-under-attack-simulation-to-enhance-fault-attacks-defenses)
- [Logic Technology and Exein](https://logic.nl/cra-compliance-scan/)
- [Nordic closing of the Memfault acquisition](https://www.inderes.fi/en/releases/nod-closing-of-acquisition-of-memfault)
- [SemiMedia on the Memfault price](https://www.semimedia.cc/nordic-acquires-iot-cloud-startup-memfault-for-120-million/)
- [Thales and esFirmware](https://www.eshard.com/blog/thales-esfirmware-security-testing)
- [Code Intelligence pricing](https://code-intelligence.com/product-pricing)
- [Code Intelligence funding](https://www.uni-bonn.de/en/research-and-teaching/transfer/transfer-center-enacom/news-folder/twelve-million-us-dollars-for-code-intelligence)
- [ONEKEY on Gartner](https://www.gartner.com/reviews/product/onekey-platform)
- [Renode repository](https://github.com/renode/renode)
- [Memfault pricing, third party](https://toolradar.com/tools/memfault/pricing)
- [CRA conformity routes, third party](https://sota.io/blog/cra-notified-body-vs-self-declaration-decision-tree-software-developer-june-2026)
- [EN 18031 harmonisation](https://www.sgs.com/news/2025/02/safeguards-02625-eu-harmonizes-en-18031-standards)
