# Discovery calls

Goal: learn whether this is a funded problem, not to sell. Ask about the past, not about what they would do. Do not show the product until the last five minutes.

## Who to talk to

Firmware leads at European makers of connected industrial products, sensors, gateways and controllers, with products on sale in the EU. Also one quality or compliance owner, and one conformity assessor or test lab.

## Firmware lead (30 minutes)

1. Walk me through what happens between a pull request and the release of a firmware update.
2. When did a security or safety bug last reach the bench or a customer? What did it cost?
3. Who is responsible for the Cyber Resilience Act here? What have they asked you for so far?
4. What security testing do you do today? When, and who runs it?
5. Do you fuzz anything? Has anyone tried fault injection? Why or why not?
6. Could your firmware's parsers build on a PC today? Does your build make an ELF you can run in an emulator?
7. Who would have to approve a new tool in CI? Can firmware leave your network?
8. What did you last pay for a test tool or an outside security review? Whose budget was it?

## Compliance or quality owner (30 minutes)

1. What product class do you believe your products fall under, and how did you decide?
2. What will go in your technical file for security testing? What is missing?
3. What would you accept as evidence from an internal tool?
4. Who outside the company will read this, if anyone?
5. What is your plan and budget for this before December 2027?

## Assessor or lab (30 minutes)

Show `EVIDENCE.md` from a real run.

1. Would you give this any weight? What would raise it?
2. What is missing for it to be useful?
3. Is evidence from an emulator a problem in itself?
4. How would you want tools like this described in a technical file?

## Close every call

- Who else should I talk to?
- If we ran this on one of your parsers for two weeks, would you pay for that? Who would sign?

## Record after each call

Problem severity (1 to 5), funded (yes or no), budget owner, product class, firmware can leave the network (yes or no), target board, and the exact words they used.
