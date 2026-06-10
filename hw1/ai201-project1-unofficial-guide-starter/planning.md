# Project 1 Planning: The Unofficial Guide

> Write this document before you write any pipeline code.
> Your spec and architecture diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Update the Retrieval Approach and Chunking Strategy sections if you change your approach during implementation.
> Update this file before starting any stretch features.

---

## Domain

<!-- What topic or category of knowledge does your system cover?
     Why is this knowledge valuable, and why is it hard to find through official channels?
     Example: "Student reviews of CS professors at [university] — useful because official
     course descriptions don't reflect teaching style, exam difficulty, or workload." -->

Lecture notes on Computer Vision and NLP. Most AI/ML courses focus on algorithms and applications, but often overlook how different sectors use these technologies. These notes cover areas like Computer Vision, Speech/Audio Processing, Natural Language Processing, and Reinforcement Learning. The PDFs compile lectures and coursework from programs that specialize in these sectors


---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | Intro to CV | PDF | documents/cap5415_intro_cv_lecture_notes |
| 2 | Advanced CV | PDF | documents/cap6412_advanced_cv_lecture_notes |
| 3 | Natural Language Processing| PDF| documents/Natural_Lanuage_Processing_CAP6614 |
| 4 | Intro ML | PDF | documents/ML_CAP5610_PDF_Slides |
| 5 | Medical Imaging| PDF | documents/cap5516_medical_imaging |
| 6 | CV Systems| PDF | documents/cap6411-CV_systems_pdf |
| 7 | Intro Stats Learning| PDF | documents/intro_stat_learning_python |
| 8 | Applied ML| PDF | documents/Applied_ML_Lectures |
| 9 | Efficient ML| PDF | documents/Efficient_ML_Slides |
| 10 | Eng. Entrprenuership| PDF | documents/Engineering_Entreprenuership_Slides |

---


## Chunking Strategy

<!-- How will you split documents into chunks?
     State your chunk size (in tokens or characters), overlap size, and explain why those
     numbers fit the structure of your documents.
     A review-heavy corpus warrants different chunking than a long FAQ. -->

**Chunk size:** 
Hybrid approach combining recursive chunking and semantic chunking:

Recursive chunking helps handle messy, real-world documents with mixed formatting and ensures the content is split meaningfully.
Semantic chunking allows the system to adapt to PDFs covering multiple topics within a sector, preserving context where topic shifts occur.

**Overlap:**
Use moderate overlap (e.g., 100–200 tokens) to maintain context across chunks, especially where topics transition.

**Reasoning:**
This hybrid method balances structural parsing and contextual understanding, ensuring that both the organization of the document and the meaning of the content are captured. Recursive chunking handles document noise, while semantic chunking ensures topic coherence, improving retrieval accuracy in a RAG setup.
---

## Retrieval Approach

<!-- Which embedding model are you using (e.g., all-MiniLM-L6-v2 via sentence-transformers)?
     How many chunks will you retrieve per query (top-k)?
     If you were deploying this for real users and cost wasn't a constraint, what tradeoffs
     would you weigh in choosing a different embedding model — context length, multilingual
     support, accuracy on domain-specific text, latency? -->


**Embedding model:**
I am using sentence-transformers/all-MiniLM-L6-v2 for generating embeddings. This model runs locally, requires no API key, is computationally efficient, and provides strong semantic search performance for a small-to-medium document corpus.

**Top-k:**
I retrieve the top 5 most similar chunks per query from ChromaDB. Retrieved chunks are further filtered using a distance/similarity threshold to reduce irrelevant context before passing results to the LLM.

**Production tradeoff reflection:**
For this project, all-MiniLM-L6-v2 offers a good balance of speed, memory usage, and retrieval quality. If deploying to production and cost were not a constraint, I would evaluate larger embedding models that provide higher retrieval accuracy, stronger multilingual support, and better performance on domain-specific text. The tradeoff is increased latency, storage requirements, and embedding computation costs. I would also consider the model's context coverage and benchmark retrieval quality on representative user queries before selecting a production embedding model.

**Pipeline:**
Document Ingestion (pdfplumber, PyPDFLoader) -> Chunking [Hybrid (Recursive + Semantic), langchain.text_splitter, chunk_size=500, chunk_overlap=50] ->  Vector Store (ChromaDB) + Embeddings [sentence-transformers (all-MiniLM-L6-v2)] -> Retrieval (Vector Search via langchain.vectorstores + Top-K + Distance Threshold), -> LLM Generation [Groq (llama-3.3-70b-versatile)]


---

## Evaluation Plan

<!-- List your 5 test questions with their expected correct answers.
     Questions should be specific enough that you can judge whether the system's response
     is right or wrong. "What are good dining halls?" is too vague.
     "What do students say about wait times at [dining hall name] during lunch?" is testable. -->

| # | Question | Expected answer |
|---|----------|-----------------|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |

---

## Anticipated Challenges

<!-- What could go wrong? Name at least two specific risks with reasoning.
     Consider: noisy or inconsistent documents, missing source attribution, off-topic
     retrieval, chunks that split key information across boundaries. -->

1.

2.

---

## Architecture

<!-- Draw a diagram of your pipeline showing the five stages:
     Document Ingestion → Chunking → Embedding + Vector Store → Retrieval → Generation
     Label each stage with the tool or library you're using.
     You can use ASCII art, a Mermaid diagram, or embed a sketch as an image.
     You'll use this diagram as context when prompting AI tools to implement each stage. -->

---

## AI Tool Plan

<!-- For each part of the pipeline below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, which requirements)
     - What you expect it to produce
     - How you'll verify the output matches your spec

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Chunking Strategy section and ask it to implement chunk_text()
     with my specified chunk size and overlap" is a plan. -->

**Milestone 3 — Ingestion and chunking:**

**Milestone 4 — Embedding and retrieval:**

**Milestone 5 — Generation and interface:**
