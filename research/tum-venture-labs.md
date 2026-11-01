# What the TUM Venture Labs Student Tech Track expects from an MVP

Research for [#138](https://github.com/JoaZaech/stetiq/issues/138), part of the map [#135](https://github.com/JoaZaech/stetiq/issues/135). Gathered 2026-11-01.

**Short answer.** The Student Tech Track (STT) is a one-year, four-sprint program run by the TUM Venture Labs *Software & AI* lab in Heilbronn. It publishes **no MVP criteria, no scoring rubric and no jury composition**. What it does publish is a phase sequence: problem discovery, then validation through customer interviews (ending in Pitch Night 1), then "a first working prototype" tested "with real users", then "a functional product and business model" pitched to investors (ending in Pitch Night 2). At the one observed Pitch Night, the format was a 7-minute pitch per team with jury feedback and no winner. So the bar at each point is set by the phase you are in, and in every phase the evidence that counts is user contact.

## What the official sources say

### The program (primary: [STT offering page](https://www.tum-venture-labs.de/offerings/student-tech-track/))

- **Shape.** The page describes STT as "a 1-year program structured into 4 phases", in "four 3-month sprints", with "a Co-Working Session every two weeks, plus regular community events". Its stated aim is that participants leave with "a functional prototype, a tested business model, and a pitch to investors".
- **Phases (verbatim headings and lines):**
  1. *Learn the basics*: "Real case studies, idea sources, and discovery material help you find a problem worth working on."
  2. *Validate*: "Market research and customer interviews turn a raw problem into a validated solution idea." "Ends with the first Pitch Night."
  3. *Prototype*: "Build a first working prototype and test it with real users."
  4. *Go-to-market*: "Turn the prototype into a functional product and business model, and prepare to pitch to investors." "Ends with the second Pitch Night."
- **Mentors.** "external active founders and domain experts". They "support teams individually throughout the whole year with regular check-ins and coaching sessions."
- **Commitment.** The commitment grows over the year: "by the later sprints - building and iterating on your prototype - expect at least 10 hours per week." Participation is in person in Heilbronn only. The program is free, and "TUM Venture Labs does not offer funding."
- **Audience.** Master's students are the primary target, with late bachelor's students also accepted. Tech, business and design backgrounds are all welcome. TUM students can register the venture as a project study (6 ECTS, Prof. Meißner).
- **Dates.** The page lists onboarding for 5 to 7 October 2026 and an application window of 15 August to 15 September. It also shows a "Join the waitlist for Batch 5!" call to action and an "STT Batch 4" timeline image, so which batch the dates belong to is ambiguous.

### Entry ([Software & AI Heilbronn lab page](https://www.tum-venture-labs.de/labs/software-ai-heilbronn/))

The page describes STT as a "semester-long journey designed for master's students". Entry has three steps: apply via form, an assessment call with the Talent Manager, then submit a use case and start. The page gives no selection criteria. It also calls STT "semester-long" while the offering page says one year. The program seems to have grown from a 16-week format (see below) to a full year.

### Pitch Nights (primary, thin)

- [STT Pitch Event page](https://www.tum-venture-labs.de/events/stt-pitch-event/): the page says five teams spent four months turning "early ideas into real concepts". It describes live pitches to students, mentors and "invited expert guests", followed by networking. It states no pitch length, no jury and no criteria.
- Eventbrite listings confirm two past Pitch Nights: [25 Jul 2025](https://www.eventbrite.de/e/student-tech-track-pitch-event-tickets-1458423376579) and [16 Jan 2026](https://www.eventbrite.de/e/student-tech-track-pitch-event-tickets-1976743178058). Neither listing gives a format.
- The January 2026 event is covered by a TUM Campus Heilbronn press release ("Student Tech Track: Students present sustainable AI projects at TUM Campus Heilbronn"). The original on chn.tum.de returns 404, and the syndicated copies ([PresseBox](https://www.pressebox.com/pressrelease/tumcampus-heilbronn-ggmbh/Student-Tech-Track-Students-present-sustainable-AI-projects-at-TUM-Campus-Heilbronn/boxid/1283442), [MyNewsChannel](https://www.mynewschannel.net/2026/01/student-tech-track-students-present-sustainable-ai-projects-at-tum-campus-heilbronn/), Software-Journal) were paywalled or under maintenance when fetched. Search-engine extracts of that release say:
  - five teams developed a deep-tech idea over 16 weeks;
  - each gave a **7-minute pitch** to a jury of the program's initiators, TUM Venture Labs and Campus Founders;
  - **no winner was named**, and the teams received feedback;
  - teams combine business, AI-engineering and software-engineering roles.

  *I could not read the release text itself, so treat these four points as secondary.*

### Adjacent bar: the UnternehmerTUM Incubator / Accelerator ([program page](https://incubator.unternehmertum.de/program/))

This is not STT, but it is the next step a TUM Venture Labs team would take, so it shows where STT leads. Screening there considers "tech implementation, market suitability, business model, team formation and product idea". Track placement depends on "team quality, venture maturity, level of validation, and investor readiness". The Creation Track works toward a testable solution or MVP logic and needs first signs of positive market feedback. The Growth Track expects an MVP already in the market ("your MVP is in the world"). The program needs at least two founders and does not admit solo founders.

## What is missing (not published anywhere I could find)

- Evaluation criteria or a rubric for Pitch Nights, and whether they are graded at all. The one observed night had no winner.
- Any definition of "MVP" or "working prototype": what must run, and for how many users.
- Jury composition, beyond the secondary press-release extract.
- Demo rules: whether a live demo is expected or allowed inside the 7 minutes.
- What the "use case" submitted at entry must contain.

All of these are best confirmed directly with the program, via software-ai.heilbronn@tum-venture-labs.de or the assigned mentor.

## Inferred (my reading, not official)

- The program is staged on validation. A Pitch Night 1 after the *Validate* sprint expects a validated problem and solution idea backed by customer interviews, not software. A working prototype belongs to sprint 3 (roughly months 7 to 9) and a "functional product" to sprint 4.
- The jury is made of founders and ecosystem people (Venture Labs, Campus Founders), so a 7-minute pitch is read as a story: problem, who has it, evidence from users, solution, business model, team. A demo inside 7 minutes is at most a 1 to 2 minute slot.
- The STT phase lines repeat "real users" and "customer interviews", and the Incubator criteria repeat "level of validation". Both reward evidence from target users more than breadth of features.

## Implications for stetiq

- **Must actually work:** one end-to-end hero flow that a prospective user (an engineer building an LLM-to-KG pipeline) can run on their own or realistic output in a few minutes. The flow is: an extraction output enters the Gate, one Consumer Gate judges fitness for that Consumer's Tasks, and an Ontology version change shows up between them. This is what "test it with real users" in sprint 3 needs, and it is the only part a jury will see live, in roughly 90 seconds.
- **Can be shown as planned:** anything off the hero path. That includes the Connector to arbitrary downstream systems, drift statistics over time, additional Consumers, a hosted multi-user deployment, and the breadth of non-hero examples. Each can appear as a roadmap slide or mock without hurting the pitch, since the program expects a "functional product" only at the end of the year.
- **Weighs as much as code:** user evidence, meaning interview notes and a pilot user or two who ran the hero flow. Also a stated business model and a team story. The program checks these at Pitch Night 1 before any prototype is due.
- **Net:** a narrow, honest, working slice plus user validation beats a broad, partly mocked product. Stetiq is already past the prototype stage the program targets for months 7 to 9, so the consolidation should cut toward one demonstrable flow rather than build more.
