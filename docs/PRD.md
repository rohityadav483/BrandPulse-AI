# BrandPulse AI
## AI-Powered Brand Intelligence MVP

> **Status:** aligned with ARCHITECTURE v2, DATABASE v2, API v2 and DEVELOPMENT_PLAN v2. Hackathon MVP, runs locally. SerpApi free plan (250 searches/month), Groq free tier, local BERT NLP. English only.

---

# 1. Problem Statement

## Problem: AI-Powered Brand Intelligence from Scattered Public Data

Businesses receive massive amounts of public feedback and market signals across YouTube, online forums, web pages, news, search trends, and shopping platforms.

This information is:

- Fragmented across different sources
- Continuously changing
- Difficult to collect manually
- Difficult to compare across competitors
- Difficult to convert into actionable business intelligence

Traditional sentiment-analysis systems mainly answer:

> **"What are people saying?"**

But businesses need to answer more important questions:

- What are customers currently talking about?
- Which product aspects are receiving positive or negative sentiment?
- Which issues are suddenly increasing?
- Is an emerging signal significant or just noise?
- Why is the signal occurring?
- Is the issue specific to our brand or affecting competitors too?
- What independent evidence supports the finding?
- What should the business do next?

## Problem Statement

> **Develop an AI-powered Brand Intelligence system that uses SerpApi as the sole external data collection layer to discover public brand conversations, market signals, news, search trends and competitor information, and uses NLP and AI reasoning to detect emerging trends, investigate their causes, validate them using independent evidence, compare competitors, and generate actionable business recommendations.**

---

# 2. Proposed Solution

## BrandPulse AI

> **An AI-powered Brand Intelligence platform that transforms scattered public information into verified, actionable business intelligence.**

The user enters a:

- Brand
- Product
- Optional competitors
- Optional analysis period

BrandPulse then uses **SerpApi as the sole external data collection layer** to collect relevant public information.

The system processes the collected information to identify:

- Sentiment
- Topics
- Product aspects
- Keywords
- Trends
- Emerging signals
- Competitor differences

When an unusual or rapidly growing signal is detected, BrandPulse launches an **AI Investigation workflow**.

The investigation:

1. Finds supporting evidence.
2. Searches for independent sources.
3. Cross-checks the signal.
4. Determines whether the issue is brand-specific or industry-wide.
5. Compares competitors.
6. Estimates impact and confidence.
7. Generates recommended business actions.

## Core Idea

> **BrandPulse AI doesn't just tell brands what people are saying. It detects what is changing, investigates why it is happening, validates the signal using live evidence, compares competitors, and tells the business what to do next.**

---

# 3. MVP Scope

The MVP should focus on one strong end-to-end workflow rather than attempting to implement every possible capability.

The product should be designed as a **clean, modern, professional business-intelligence SaaS application** with a consistent **white-and-blue visual theme**.

## Primary MVP workflow

```text
Brand Input
     ↓
Collect Public Data
     ↓
Clean & Normalize
     ↓
Sentiment + Topic + Aspect Analysis
     ↓
Detect Emerging Signals
     ↓
Investigate Important Signal
     ↓
Collect Independent Evidence
     ↓
Compare Competitors
     ↓
Generate Recommendation
     ↓
Display Intelligence Dashboard
```

## MVP priorities

### Must Have

- Brand search
- Public data collection through SerpApi
- Data normalization
- Sentiment analysis
- Topic extraction
- Aspect extraction
- Basic trend detection
- Emerging-signal detection
- AI investigation
- Evidence collection
- Source attribution
- Competitor comparison
- AI recommendations
- Interactive dashboard
- Responsive design
- Consistent white-and-blue visual identity

### Visual Design Requirements

The entire MVP must follow a **white-and-blue professional SaaS theme**.

**Primary visual language:**

- White as the primary background
- Blue as the primary brand/accent color
- Very light blue for secondary backgrounds and highlighted sections
- Dark navy/charcoal for primary text
- Light gray/blue borders
- White cards with subtle shadows
- Blue primary buttons and interactive elements
- Blue-based charts and data visualizations
- Consistent blue accent throughout navigation, cards, charts, buttons and status elements

**Design style:**

- Clean
- Modern
- Professional
- Minimal
- Data-focused
- Spacious
- Easy to scan
- Business-intelligence/SaaS aesthetic

**Avoid:**

- Dark-mode-first design
- Purple/pink as primary colors
- Excessive gradients
- Excessive glassmorphism
- Neon colors
- Unnecessary animations
- Random accent colors
- Visually cluttered dashboards

### Status and Alert Colors

Blue should remain the dominant product color, but semantic colors may be used when necessary.

```text
Blue    → Primary / information / normal state
Green   → Positive / success
Yellow  → Warning / moderate concern
Red     → High-risk / critical signal
Gray    → Neutral / inactive
```

Red, yellow and green should be used **only for semantic meaning**, not as general design colors.

For example:

```text
🚨 HIGH IMPACT
```

may use red because it represents a high-risk signal, while the rest of the dashboard remains white and blue.

### Emerging Signal Design

The **Emerging Signal** card should be one of the visual focal points of the dashboard.

Example:

```text
┌──────────────────────────────────────────────┐
│  🚨  EMERGING SIGNAL                         │
│                                              │
│  Battery complaints                          │
│  ↑ 4.2× this period                         │
│                                              │
│  Confidence       87%                        │
│  Impact           HIGH                       │
│  Sources          4                          │
│                                              │
│                 [ Investigate ]              │
└──────────────────────────────────────────────┘
```

The card should retain the overall white-and-blue design while using a restrained red indicator for the high-impact status.

### Dashboard Design Principles

The dashboard should prioritize:

1. **Signal visibility**
2. **Evidence transparency**
3. **Actionability**
4. **Easy comparison**
5. **Minimal cognitive load**

The user should immediately understand:

> **What is happening → Why it is happening → How confident we are → What evidence supports it → What should we do.**

## Not required initially

The following should **not** be mandatory for the first MVP:

- Redis
- Multiple independent microservices
- Complex multi-agent infrastructure
- Dedicated vector database
- Large-scale distributed processing
- Continuous background monitoring
- Complex authentication
- Enterprise-scale deployment
- Advanced model training
- Extensive animation systems
- Multiple UI component libraries
- Dark-mode implementation

These can be added later if the MVP requires them.

## MVP Design Goal

The final MVP should feel like a **real professional Brand Intelligence SaaS product**, not a collection of AI-generated screens.

The visual identity should remain consistent across:

```text
Landing Page
     ↓
Brand Search
     ↓
Analysis
     ↓
Dashboard
     ↓
Emerging Signals
     ↓
Investigation
     ↓
Evidence
     ↓
Competitor Analysis
     ↓
Recommendations
```

Every page should use the same **white-and-blue BrandPulse design system**.

---

# 4. Architecture

```text
                         ┌───────────────────┐
                         │       USER        │
                         │ Brand / Product   │
                         └─────────┬─────────┘
                                   │
                                   ▼
                    ┌─────────────────────────┐
                    │       NEXT.JS           │
                    │ TypeScript + Tailwind   │
                    │       shadcn/ui         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │        FASTAPI          │
                    │      API Layer          │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐    ┌─────────────┐   ┌─────────────┐
       │   SerpApi   │    │  Supabase   │   │    LLM      │
       │ Data Layer  │    │ PostgreSQL  │   │ Reasoning   │
       └──────┬──────┘    └─────────────┘   └─────────────┘
              │
              ▼
       ┌─────────────────────┐
       │ Data Processing     │
       │ Cleaning            │
       │ Normalization       │
       │ Deduplication       │
       │ Attribution         │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ NLP / Analytics     │
       │                     │
       │ Sentiment           │
       │ Topics              │
       │ Aspects             │
       │ Keywords            │
       │ Trends              │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ Signal Detection    │
       │                     │
       │ Growth              │
       │ Velocity            │
       │ Frequency           │
       │ Cross-source        │
       └──────────┬──────────┘
                  │
                  ▼
          ┌──────────────────┐
          │ Emerging Signal  │
          └────────┬─────────┘
                   │
                   ▼
       ┌─────────────────────┐
       │ Investigation Agent │
       │                     │
       │ Why is this        │
       │ happening?         │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ Evidence            │
       │ Verification        │
       │                     │
       │ Cross-source        │
       │ Confidence          │
       │ Attribution         │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ Competitor Analysis │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ Recommendations     │
       └──────────┬──────────┘
                  │
                  ▼
       ┌─────────────────────┐
       │ BrandPulse          │
       │ Dashboard           │
       └─────────────────────┘
```

---

# 5. Simplified Architecture Philosophy

The MVP should be built as a **modular monolith**, not as a collection of independent microservices.

This makes it much easier to vibe-code, test, debug and deploy.

The backend can contain modules such as:

```text
backend/
├── api/
├── services/
│   ├── serpapi/
│   ├── processing/
│   ├── nlp/
│   ├── llm/
│   ├── scoring/
│   ├── signals/
│   ├── investigation/
│   ├── competitors/
│   └── recommendations/
├── models/
├── database/
└── utils/
```

The modules remain logically separated while the application stays simple.

---

# 6. SerpApi Data Layer

SerpApi is the **only external data/API provider** used for public-data collection.

```text
SerpApi
├── Google Search
├── Google News
├── Google Trends
├── Google Shopping
├── Google Forums
├── YouTube Search
├── YouTube Video
├── YouTube Channel
├── Search Index
└── Instagram Profile
```

## API roles

| SerpApi Source | Purpose |
|---|---|
| YouTube Search | Discover relevant videos |
| YouTube Video | Retrieve relevant video information (only if budget allows) |
| YouTube Channel | Analyze relevant creators/channels (cut from MVP) |
| Google Forums | Discover forum/community discussions |
| Google Search | General brand research |
| Google News | Identify news/events |
| Google Trends | Validate search-interest changes |
| Google Shopping | Product/pricing/market information (optional, late) |
| Search Index | Deep web research (cut from MVP) |
| Instagram Profile | Optional supplementary signal (cut from MVP) |

The system should avoid adding separate external data APIs during the MVP. The SerpApi free plan allows 250 searches per month, so the design is budget-first (see ARCHITECTURE.md §6).

---

# 7. Data Collection Strategy

The system should not attempt to collect unlimited data.

For each brand analysis:

```text
1. Identify brand
2. Generate relevant queries
3. Query selected SerpApi sources
4. Collect results
5. Normalize results
6. Remove duplicates
7. Store source metadata
8. Analyze collected information
```

Each data item should retain:

```text
source
source_url
title
content/snippet
published_date
author/channel where available
brand
query
collection_timestamp
```

This enables evidence tracing later.

---

# 8. Data Processing

Before analysis, collected information passes through a processing layer.

## Processing steps

### 1. Cleaning

Remove:

- Empty results
- Invalid records
- Irrelevant content
- Duplicate text
- Unusable metadata

### 2. Normalization

Convert different sources into a common structure.

```text
{
    source,
    title,
    content,
    url,
    timestamp,
    brand,
    metadata
}
```

### 3. Deduplication

Avoid counting the same information multiple times.

### 4. Source Attribution

Every insight should retain the source information from which it originated.

---

# 9. NLP and AI Layer

The MVP should use existing models rather than training models from scratch.

## 9.1 Sentiment Analysis

Use a BERT-family/Transformer-based sentiment model, run locally on CPU (no LLM in the analysis path).

Output:

```text
Positive
Neutral
Negative
```

Example:

```text
"The phone feels premium but the battery is terrible."

Overall:
Neutral (mixed signals)

Aspect:
Design → Positive
Battery → Negative
```

---

# 10. Topic Extraction

The MVP should identify major discussion themes.

Example:

```text
Battery
Camera
Performance
Pricing
Design
Software
Customer Support
```

BERTopic is deferred (post-MVP). Topics = aspects plus top keywords.

For the first MVP, the implementation should prioritize reliability and simplicity over sophisticated topic-modeling infrastructure.

---

# 11. Aspect-Based Sentiment

Aspect-level analysis is one of the most important capabilities.

Example:

```text
"The camera is amazing but battery life is terrible."
```

Output:

```text
Camera
Sentiment: Positive

Battery
Sentiment: Negative
```

This allows BrandPulse to move beyond simple overall sentiment.

---

# 12. Embeddings

Sentence Transformers are deferred (post-MVP). They could later be used for:

- Semantic similarity
- Duplicate detection
- Similar complaint detection
- Clustering
- Evidence matching

For the MVP, embeddings should be introduced only where they provide a clear benefit.

---

# 13. Vector Search

FAISS is deferred (post-MVP).

If semantic evidence retrieval becomes necessary:

```text
Content
   ↓
Sentence Transformer
   ↓
Embedding
   ↓
FAISS
   ↓
Similar evidence
```

Otherwise, normal database/search-based retrieval should be used.

This keeps the first implementation simpler.

---

# 14. Signal Detection

The **Emerging Signal Engine** is the core intelligence component.

The system should identify signals using measurable indicators such as:

- Frequency
- Growth
- Velocity
- Sentiment change
- Topic frequency change
- Cross-source occurrence
- Search-interest change

## Example

Historical period:

```text
Battery complaints: 20
```

Current period:

```text
Battery complaints: 84
```

Growth:

```text
4.2×
```

The system can flag:

```text
🚨 Emerging Signal

Battery complaints
↑ 4.2×

Impact: HIGH
Confidence: 87%
Sources: 4
```

The MVP can use a transparent scoring formula rather than a complex ML model.

Example:

```text
Signal Score =
    Growth Score
    + Frequency Score
    + Cross-source Score
    + Sentiment Impact
```

The exact weights can be tuned during development.

---

# 15. Investigation Agent

When a signal crosses a defined threshold, the system launches an AI investigation.

Example:

```text
Signal:
Battery complaints increased 4.2×
```

The investigation agent asks:

> **Why is this happening?**

It then performs additional SerpApi searches.

```text
Emerging Signal
      ↓
Generate investigation queries
      ↓
SerpApi
      ↓
YouTube
Forums
News
Search
Trends
      ↓
Collect evidence
      ↓
Cross-check
      ↓
Generate explanation
```

The investigation should not simply accept the first explanation it finds.

---

# 16. Evidence Verification

Every important AI finding should have supporting evidence.

The system should provide:

- Source
- Title
- URL
- Relevant content/snippet
- Source type
- Collection time
- Relationship to the finding

Example:

```text
Finding:
Battery complaints increased significantly.

Supporting evidence:

✓ YouTube discussions
✓ Forum discussions
✓ Web discussions
✓ News coverage
✓ Search-interest increase
```

---

# 17. Confidence Score

The system should estimate confidence based on evidence quality.

Factors can include:

```text
Number of independent sources
+
Cross-source agreement
+
Signal strength
+
Recency
+
Consistency
```

Example:

```text
Confidence: 87%
```

The confidence score should be presented as an analytical estimate, not as an absolute truth.

---

# 18. Competitor Analysis

BrandPulse should determine whether a signal is:

```text
Brand-specific
        OR
Industry-wide
```

Example:

```text
                 Samsung    Apple    OnePlus

Positive          62%        74%       69%
Negative          17%        11%       13%

Battery Issues    HIGH       LOW       MEDIUM

Search Interest   ↑31%       ↑8%       ↑12%
```

This answers:

> **Is this actually a brand problem or an industry-wide problem?**

Competitor data should be collected through the same SerpApi layer.

---

# 19. AI Recommendations

The system should convert findings into business actions.

Example:

```text
RECOMMENDED ACTIONS

1. Investigate battery performance after
   the latest software update.

2. Monitor battery-related complaints
   over the next 7 days.

3. Prepare customer-support messaging
   addressing the issue.

4. Compare competitor battery perception
   before launching the next campaign.

Priority: HIGH
```

Recommendations should be directly linked to the findings and evidence rather than generic AI suggestions.

---

# 20. LLM Layer

Use one LLM provider for the MVP: **Groq (free tier)**, used only for investigation reasoning. Sentiment and aspect analysis run locally, not through the LLM.

The LLM is responsible for:

- Investigation reasoning
- Evidence synthesis
- Root-cause analysis
- Natural-language explanations
- Recommendations
- Report generation

The architecture should keep the LLM provider replaceable.

```text
LLM Service
     ↓
generate_queries()
tag_stance()
synthesize()
recommend()
suggest_competitors()
```

This prevents the rest of the application from being tightly coupled to a specific model.

---

# 21. Database

Use **Supabase PostgreSQL** for the MVP.

This avoids separately managing PostgreSQL infrastructure.

## Main entities

```text
Brands
Products
Sources
Content
Topics
Sentiments
Aspects
Signals
Evidence
Competitors
Recommendations
Analyses
```

Schema (details in DATABASE.md; no separate products or competitors tables):

```text
brands
analyses
analysis_brands
serp_cache
serp_usage
content_items
content_analysis
item_aspects
trend_points
brand_snapshots
signals
investigations
evidence
recommendations
llm_calls
```

Supabase can also provide authentication and storage if required later.

---

# 22. Redis

**Do not use Redis in the initial MVP.**

It can be introduced later for:

- Caching SerpApi results
- Background jobs
- Queues
- Rate-limit management

The MVP should first work without it.

---

# 23. Frontend Technology Stack

## Recommended

### Next.js

Used for:

- Dashboard
- Routing
- Pages
- UI integration
- Server-side functionality where useful

### TypeScript

Used throughout the frontend for type safety.

### Tailwind CSS

Used for styling.

### shadcn/ui

Used for reusable UI components.

## Frontend stack

```text
Next.js
+
TypeScript
+
Tailwind CSS
+
shadcn/ui
```

This stack is intentionally chosen because it is highly suitable for AI-assisted development and rapid MVP construction.

---

# 24. Dashboard

The dashboard should contain six major outputs.

---

## 24.1 Brand Health Score

```text
BRAND HEALTH

73 / 100

Sentiment       72
Engagement      81
Risk            64
Trend Health    76
```

The exact scoring formula should be documented and consistent.

---

# 25. Sentiment and Aspect Analysis

Example:

```text
OVERALL SENTIMENT

Positive     62%
Neutral      21%
Negative     17%
```

Aspect breakdown:

```text
Aspect               Sentiment

Camera                 +82%
Performance            +76%
Design                 +71%
Battery                -48%
Software               +61%
Customer Support       -32%
```

The user should be able to click an aspect and inspect supporting evidence.

---

# 26. Emerging Trends

This should be the **hero feature of the MVP**.

Example:

```text
🚨 EMERGING SIGNAL

Battery complaints

↑ 4.2× this period

Confidence: 87%
Impact: HIGH
Sources: 4

[Investigate]
```

Clicking **Investigate** starts the AI investigation workflow.

---

# 27. AI Investigation Report

Example:

```text
WHY IS THIS HAPPENING?

The increase in battery-related complaints
appears to be associated with recent software
changes.

Supporting evidence:

✓ YouTube discussions
✓ Forum discussions
✓ Web discussions
✓ News coverage
✓ Search-interest increase

Confidence: 87%
```

The report must include source links/citations back to the underlying SerpApi-derived sources.

---

# 28. Competitor Intelligence

Example:

```text
                    Samsung    Apple    OnePlus

Positive             62%        74%       69%
Negative             17%        11%       13%

Battery Issues       HIGH       LOW       MEDIUM

Search Interest      ↑31%       ↑8%       ↑12%
```

The competitor section should answer:

> **Is this a problem with our brand specifically, or is the entire market experiencing it?**

---

# 29. AI Business Recommendations

Example:

```text
RECOMMENDED ACTIONS

1. Investigate battery performance after
   the latest software update.

2. Monitor battery-related complaints
   over the next 7 days.

3. Prepare customer-support messaging
   addressing the issue.

4. Compare competitor battery perception
   before launching the next campaign.

Priority: HIGH
```

---

# 30. Source and Evidence Explorer

Every important insight should be traceable.

The user should be able to open:

```text
Signal
   ↓
Evidence
   ↓
Source
   ↓
Original URL
```

This makes the platform more credible than a simple AI-generated dashboard.

---

# 31. Recommended Project Structure

## Frontend

```text
frontend/
├── app/
│   ├── dashboard/
│   ├── analyze/
│   ├── signals/
│   ├── competitors/
│   └── evidence/
├── components/
│   ├── dashboard/
│   ├── signals/
│   ├── competitors/
│   ├── evidence/
│   └── ui/
├── lib/
├── types/
└── public/
```

## Backend

```text
backend/
├── app/
│   ├── api/v1/
│   ├── schemas/
│   ├── pipeline/
│   ├── services/
│   │   ├── serpapi/
│   │   ├── processing/
│   │   ├── nlp/
│   │   ├── llm/
│   │   ├── scoring/
│   │   ├── signals/
│   │   ├── investigation/
│   │   ├── competitors/
│   │   └── recommendations/
│   ├── models/
│   ├── database/
│   ├── config/
│   └── utils/
└── tests/
```

The structure should remain simple and modular.

---

# 32. API Flow

Base path `/api/v1`. Full spec in API.md (also `POST /analyses/estimate` and `GET /usage` for the SerpApi budget).

Example:

```text
POST /analyses
        ↓
Create analysis
        ↓
Collect SerpApi data
        ↓
Process data
        ↓
Run NLP
        ↓
Detect signals
        ↓
Store results
        ↓
Return analysis ID
```

Then:

```text
GET /analyses/{id}/dashboard
```

returns the dashboard data.

For investigation:

```text
POST /signals/{id}/investigate
```

The backend then:

```text
Signal
 ↓
Generate queries
 ↓
SerpApi
 ↓
Evidence
 ↓
LLM analysis
 ↓
Competitor comparison
 ↓
Recommendation
```

---

# 33. MVP Data Flow

```text
                    USER
                     │
                     ▼
               Enter Brand
                     │
                     ▼
               Create Analysis
                     │
                     ▼
                  FastAPI
                     │
                     ▼
                  SerpApi
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
     Search        YouTube        News
       │             │              │
       └─────────────┼──────────────┘
                     ▼
              Normalize Data
                     │
                     ▼
              NLP Processing
                     │
          ┌──────────┼───────────┐
          ▼          ▼           ▼
      Sentiment    Topics      Aspects
          │          │           │
          └──────────┼───────────┘
                     ▼
              Signal Detection
                     │
                     ▼
              Emerging Signal
                     │
                     ▼
               Investigation
                     │
                     ▼
                  SerpApi
                     │
                     ▼
             Evidence Collection
                     │
                     ▼
           Competitor Comparison
                     │
                     ▼
              AI Recommendation
                     │
                     ▼
                Dashboard
```

---

# 34. Killer Demo Flow

The entire hackathon demonstration should focus on one compelling scenario.

## Step 1 — User enters brand

```text
Samsung
```

Optional competitors:

```text
Apple
OnePlus
```

---

## Step 2 — Collect public data

BrandPulse uses SerpApi to collect relevant:

- Search results
- YouTube information
- Forum discussions
- News
- Trends

---

## Step 3 — Analyze

The NLP pipeline identifies:

```text
Battery
Camera
Performance
Software
Pricing
Customer Support
```

---

## Step 4 — Detect signal

The system detects:

```text
🚨 EMERGING SIGNAL

Battery complaints
↑ 4.2×
```

The signal is classified:

```text
Impact: HIGH
Confidence: 87%
Sources: 4
```

---

## Step 5 — User clicks Investigate

```text
[ INVESTIGATE ]
```

The investigation workflow starts.

---

## Step 6 — AI investigates

The system generates additional searches and uses SerpApi to find:

```text
YouTube
+
Forums
+
News
+
Web
+
Trends
```

---

## Step 7 — Evidence verification

The system cross-checks the findings.

```text
Evidence found across:

✓ YouTube
✓ Forums
✓ Web
✓ News
✓ Search Trends
```

---

## Step 8 — Competitor comparison

The system determines:

```text
Samsung → HIGH battery complaints
Apple   → LOW
OnePlus → MEDIUM
```

This suggests the signal may be more brand-specific rather than purely industry-wide.

---

## Step 9 — AI explanation

Example:

```text
WHY IS THIS HAPPENING?

The increase in battery-related complaints
appears to be associated with recent software
changes.

Confidence: 87%
```

The explanation must show the evidence supporting the conclusion.

---

## Step 10 — Recommendation

```text
RECOMMENDED ACTIONS

1. Investigate battery performance after
   the latest software update.

2. Monitor battery-related complaints.

3. Prepare customer-support messaging.

4. Compare competitor battery perception.

Priority: HIGH
```

---

# 35. Final Dashboard

The final dashboard should present:

```text
┌──────────────────────────────────────────────┐
│              BRANDPULSE AI                   │
├──────────────────────────────────────────────┤
│                                              │
│ Brand Health         73 / 100                │
│                                              │
│ Sentiment            62% Positive            │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │ 🚨 EMERGING SIGNAL                       │ │
│ │                                          │ │
│ │ Battery complaints ↑ 4.2×               │ │
│ │                                          │ │
│ │ Impact: HIGH                             │ │
│ │ Confidence: 87%                          │ │
│ │                                          │ │
│ │              [ INVESTIGATE ]             │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ Topics          Competitors                 │
│                                              │
│ Evidence        Recommendations             │
│                                              │
└──────────────────────────────────────────────┘
```

The **Emerging Signal → Investigate → Evidence → Recommendation** flow should receive the most visual emphasis.

---

# 36. Technology Stack

## Frontend

```text
Next.js
TypeScript
Tailwind CSS
shadcn/ui
```

## Backend

```text
Python
FastAPI
```

## Database

```text
Supabase
PostgreSQL
```

## External Data

```text
SerpApi
```

## NLP

```text
Transformers
BERT-family model (local, CPU)
```

## Topic Analysis

```text
BERTopic
```

Deferred (post-MVP).

## Vector Search

```text
FAISS
```

Deferred (post-MVP).

## LLM

```text
Groq (free tier, one provider)
```

Used for:

- Investigation
- Evidence synthesis
- Root-cause reasoning
- Recommendations
- Report generation

---

# 37. Development Stack for Vibe Coding

The development workflow should remain intentionally minimal.

```text
Claude Web
     │
     │ Planning / architecture /
     │ code generation / review
     ▼
Antigravity
     │
     │ Build / modify / run /
     │ test / debug
     ▼
GitHub
     │
     │ Version control
     ▼
Supabase
     │
     │ Database / Auth / Storage
     ▼
BrandPulse AI
```

The project should not require a large collection of development tools.

---

# 38. Development Strategy

> Superseded by DEVELOPMENT_PLAN.md (phases 0–10). The outline below is the original sketch.

Do not ask the coding agent to build the entire application in one step.

Build incrementally.

## Phase 1 — Project setup

```text
Next.js
FastAPI
Supabase
GitHub
```

Get the basic application running.

---

## Phase 2 — Dashboard

Build:

- Navigation
- Brand input
- Dashboard layout
- Cards
- Charts
- Signal component
- Evidence component

Use mock data initially.

---

## Phase 3 — SerpApi integration

Implement:

```text
SerpApi client
↓
Search
↓
Normalize results
↓
Store results
```

Test this independently.

---

## Phase 4 — NLP

Implement:

```text
Sentiment
Topics
Aspects
Keywords
```

---

## Phase 5 — Signal detection

Implement:

```text
Frequency
Growth
Velocity
Cross-source detection
Signal score
```

---

## Phase 6 — Investigation

Implement:

```text
Signal
↓
Generate investigation queries
↓
SerpApi
↓
Evidence
↓
LLM
↓
Explanation
```

---

## Phase 7 — Competitor analysis

Implement:

```text
Brand
vs
Competitors
```

---

## Phase 8 — Recommendations

Generate business actions based on:

```text
Signal
+
Evidence
+
Competitor context
```

---

## Phase 9 — Testing

Test:

- SerpApi failures
- Empty search results
- Duplicate data
- Invalid data
- LLM failures
- Rate limits
- Missing evidence
- Incorrect competitor data
- API failures
- Database failures

---

## Phase 10 — Demo polish

Only after the functionality works:

- Improve dashboard
- Add animations
- Improve charts
- Improve loading states
- Add error messages
- Improve evidence display
- Polish the investigation experience

---

# 39. MVP Success Criteria

The MVP is successful if a user can:

```text
Enter a brand
      ↓
Collect public information
      ↓
See sentiment/topics/aspects
      ↓
See an emerging signal
      ↓
Click Investigate
      ↓
See independent evidence
      ↓
See competitor comparison
      ↓
Understand why the signal is occurring
      ↓
Receive an actionable recommendation
```

The complete flow should work end-to-end.

---

# 40. What NOT to Overbuild

For the first version, avoid:

```text
❌ Microservices
❌ Kubernetes
❌ Redis
❌ Complex queues
❌ Multiple databases
❌ Multiple vector databases
❌ Custom ML model training
❌ Multiple LLM providers
❌ Complex multi-agent frameworks
❌ Real-time streaming infrastructure
❌ Enterprise authentication
❌ Large-scale distributed processing
```

The goal is:

> **One repository + one frontend + one backend + one database + one external data provider + one LLM.**

---

# 41. Final Product Architecture

```text
                         BRANDPULSE AI
                              │
                    ┌─────────┴─────────┐
                    │                   │
                 Frontend            Backend
                    │                   │
                 Next.js             FastAPI
                    │                   │
          ┌─────────┴──────┐    ┌───────┴────────┐
          │                │    │                │
      Dashboard         UI      SerpApi        LLM
          │                       │                │
          │                       ▼                │
          │                  Public Data           │
          │                       │                │
          │                       ▼                │
          │                Data Processing         │
          │                       │                │
          │                       ▼                │
          │                NLP / Analytics         │
          │                       │                │
          │                       ▼                │
          │                Signal Detection        │
          │                       │                │
          │                       ▼                │
          │                Investigation ──────────┘
          │                       │
          │                       ▼
          │                Evidence Verification
          │                       │
          │                       ▼
          │                Competitor Analysis
          │                       │
          │                       ▼
          │                 Recommendations
          │                       │
          └───────────────────────┘
                              │
                              ▼
                         Supabase
                         PostgreSQL
```

---

# 42. Final Product Positioning

BrandPulse AI should not be positioned as simply:

> "An AI sentiment-analysis dashboard."

Instead:

> **BrandPulse AI is an AI-powered brand intelligence system that detects emerging public signals, investigates why they are happening, validates them with independent live evidence, compares competitors, and recommends what businesses should do next.**

The strongest product story is:

```text
WHAT IS CHANGING?
        ↓
WHY IS IT HAPPENING?
        ↓
IS IT REALLY SIGNIFICANT?
        ↓
IS IT OUR PROBLEM OR THE MARKET'S?
        ↓
WHAT SHOULD WE DO?
```

## Final one-line pitch

> **BrandPulse AI turns scattered public data into verified business intelligence by detecting what is changing, investigating why, validating the evidence, comparing competitors, and recommending what to do next.**

---

# 43. MVP Constraints (v2)

```text
Hackathon MVP, local run only (no hosting)
SerpApi free plan: 250 searches/month, shared by dev, test and demo
Groq free tier: tight limits, deterministic fallback when quota is gone
Max 2 competitors per analysis
Pinned demo: Samsung Galaxy S25 Ultra, as_of_date 2026-08-10
Fallback ladder: live → cached (pre-warmed) → demo bundle
English only
```