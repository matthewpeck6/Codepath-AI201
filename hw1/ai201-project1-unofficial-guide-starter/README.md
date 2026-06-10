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
## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | can you describe the Transformer Basics building blocks| Encoder and Decoder Blocks containing Self-Attention, Layer Normalization, and Feed Forward Network. The decoder alos has the final activation layer and softmax probability function to create its output layers.| Encoder and Decoder Blocks containing Self-Attention, Layer Normalization, and Feed Forward Network| Relevant | Accurate
| 2 | How does an autoencoder differ from PCA for dimensionality reduction?| • PCA produce smaller set of vectors, Approximate the input vectors via linear combination, Very efficient for certain applications. • Autoencoder Can learn nonlinear dependencies, Can use convolutional layers, and Can use transfer learning. 
| An autoencoder differs from PCA for dimensionality reduction in that it can learn nonlinear dependencies, whereas PCA produces a smaller set of vectors via linear combination. Additionally, autoencoders can use convolutional layers and transfer learning, making them more flexible and capable of handling complex data. In contrast, PCA is very efficient for certain applications but limited to linear relationships.| Relevant | Accurate|
| 3 | What are the main applications of autoencoders in computer vision?| Transfer Learning, Denoising, Image colorization, Anomaly detection, Feature Learning| Image retrieval and dimensionality reduction, which helps in certain applications. They can also be used for feature learning. . Additionally, autoencoders can learn nonlinear dependencies and can be used with convolutional layers and transfer learning| Partially Relevant| Patially Accurate|
| 4 | What is positional encoding and why do transformers need it? | Transformer process tokens in
parallel by adding a vector to each input embedding. These vectors follow a specific pattern that the model Learned pattern helps model: to determine the position of each word, or the distance between different words| Transformers need positional encoding because they are permutation invariant and process tokens in parallel, which means the attention mechanism does not take into account the position of a word in the sequence. Positional encoding is necessary to enable the transformer to understand the context and position of each word. | Partially Relevant| Accurate|
| 5 | What is the encoder-decoder architecture used for? | It is used for  sequence-to-sequence (seq2seq) tasks consisting of two parts: an encoder that reads and compresses input data into a unified context, and a decoder that uses that context to generate a brand-new output sequence.| The encoder-decoder architecture is used for text-to-text tasks, such as summarization and translation, as well as for representation learning and embedding learning. It is also used in models like T5 and BART.| Relevant| Accurate|

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:**
What is self-attention and how does it work in transformers?

**What the system returned:**
self-attention is listed as a topic in the content section, along with Query, Key, Value, which are related concepts.

**Root cause (tied to a specific pipeline stage):**
Some of the information is contained in Latex or Images requiriring OCR to parse. Furthermore, the information may be mentioned but not fully explained the presentation slides. Finally, the model is not trained to interpret the images.

**What you would change to fix it:**
WIth more time, I would add EasyOCR and LaTeX-OCRto parse through images and latex code respectively. 

---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:**

**One way your implementation diverged from the spec, and why:**

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI:*
<!-- Based on my Chunking Strategy and Pipeline below:
**Chunk size:** 
Hybrid approach combining recursive chunking and semantic chunking:

Recursive chunking helps handle messy, real-world documents with mixed formatting and ensures the content is split meaningfully.
Semantic chunking allows the system to adapt to PDFs covering multiple topics within a sector, preserving context where topic shifts occur.

**Overlap:**
Use moderate overlap (e.g., 100–200 tokens) to maintain context across chunks, especially where topics transition.

**Reasoning:**
This hybrid method balances structural parsing and contextual understanding, ensuring that both the organization of the document and the meaning of the content are captured. Recursive chunking handles document noise, while semantic chunking ensures topic coherence, improving retrieval accuracy in a RAG setup.

implement a script that loads your documents, cleans them, and produces chunks matching your specified chunk size and overlap.  it should match your spec and  handle the document structure example described here where the documents are pdf file types.
-->
- *What it produced:* <!-- Code for Chunking and RAG Pipeline  -->
- *What I changed or overrode:*<!-- File_path directory, Groq API Key, chunkinig sizes and -->


**Instance 2**

- *What I gave the AI:* <!-- Use the attached planning.md and pipeline diagram to prompt an AI tool to generate the generation and interface code. Your prompt should include: your grounding requirement (answers from retrieved context only, with source attribution), the output format you want (answer + source list), and the Gradio skeleton structure if you're using it. Ask the AI to wire it all together. Before running the generated code, read through it — make sure the system prompt actually enforces grounding, not just suggests it, and that source attribution is programmatically guaranteed rather than left to the LLM to add on its own. Connect to your LLM. The recommended default is Groq's llama-3.3-70b-versatile, which is free-tier and OpenAI-compatible — initialize it with from groq import Groq and your GROQ_API_KEY from .env. Write a prompt template that passes the retrieved chunks as context and explicitly instructs the model to answer only from that context. -->
- *What it produced:* <!-- Building Block Code for launch and web design of LLM -->

- *What I changed or overrode:* <!-- Local vs Public Launch, Revised Order of code so ingest_and_chunk is ran first for ChromaDB to have data, chunkinig sizes and -->
