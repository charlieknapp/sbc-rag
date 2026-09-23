import json

import streamlit as st

from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.embedding_retriever import EmbeddingRetriever
from src.generation.pipeline import answer_question

st.set_page_config(page_title="SBC RAG", page_icon="🩺", layout="centered")


@st.cache_resource
def load_retrievers():
    bm25 = BM25Retriever()
    embedding = EmbeddingRetriever()
    return bm25, embedding


@st.cache_data
def load_eval_questions():
    with open("eval/questions.jsonl") as f:
        return [json.loads(line) for line in f if line.strip()]


bm25, embedding = load_retrievers()

st.title("SBC Plan Q&A")
st.caption(
    "Ask a question about one of 8 real health insurance plans (Kaiser, Aetna, "
    "UnitedHealthcare, Cigna, Blue Shield of CA, BCBS IL, Anthem, Highmark BCBS). "
    "Every answer is grounded in the plans' actual SBC documents and cited."
)

question = st.text_input("Ask a question:", placeholder="e.g. What is the deductible for the Kaiser plan?")
submitted = st.button("Ask", type="primary")

if submitted and question.strip():
    with st.spinner("Thinking..."):
        pipeline_result = answer_question(question, bm25, embedding)
    result = pipeline_result.result

    if result.confident:
        st.success("Confident")
    else:
        st.warning("Not confident")

    st.write(result.answer)

    if result.citations:
        st.subheader("Citations")
        for c in result.citations:
            badge = "verified data" if c.source_type == "verified_plan_data" else "SBC text"
            st.markdown(f"- **{c.insurer}** — {c.plan_name}  \n  `{c.source_filename}` · {c.section} · *{badge}*")

    if pipeline_result.verification_issues:
        st.error("Citation verification issues: " + "; ".join(pipeline_result.verification_issues))

    m = pipeline_result.metrics
    st.caption(f"{m.latency_seconds:.2f}s · {m.input_tokens + m.output_tokens} tokens · ${m.estimated_cost_usd:.4f}")

st.divider()

with st.expander("Run the full 27-question eval set"):
    st.write(
        "Runs every question in `eval/questions.jsonl` through the pipeline. "
        "Takes about 90 seconds and costs roughly $0.22 in API usage."
    )
    if st.button("Run full eval"):
        questions = load_eval_questions()
        progress = st.progress(0.0)
        rows = []
        total_latency = total_input = total_output = total_cost = 0.0

        for i, q in enumerate(questions):
            pipeline_result = answer_question(q["question"], bm25, embedding)
            result = pipeline_result.result
            rows.append({
                "id": q["id"],
                "question": q["question"],
                "confident": result.confident,
                "answer": result.answer,
                "citations": len(result.citations),
                "issues": len(pipeline_result.verification_issues),
            })
            total_latency += pipeline_result.metrics.latency_seconds
            total_input += pipeline_result.metrics.input_tokens
            total_output += pipeline_result.metrics.output_tokens
            total_cost += pipeline_result.metrics.estimated_cost_usd
            progress.progress((i + 1) / len(questions))

        st.dataframe(rows, use_container_width=True)
        st.caption(f"Totals: {total_latency:.2f}s · {total_input + total_output} tokens · ${total_cost:.4f}")