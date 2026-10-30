"""Deterministic DEMO question bank. These are fixed, hand-written fixture questions — NOT live or
LLM-generated content — and every assessment drawn from them is labelled `generation_source="demo_bank"`.
Answer keys (correct option, rubric patterns) exist only here and in the DB, never in a user-facing schema."""

from dataclasses import dataclass

from app.assessments.grading import Criterion
from app.models.enums import Difficulty, QuestionType

B, M = Difficulty.BEGINNER, Difficulty.INTERMEDIATE


@dataclass(frozen=True)
class QuestionSpec:
    type: QuestionType
    difficulty: Difficulty
    text: str
    options: tuple[str, ...] = ()  # MCQ option texts, ids A..D by position
    correct: str | None = None  # MCQ option id
    criteria: tuple[Criterion, ...] = ()


def _mcq(text: str, options: tuple[str, str, str, str], correct: str, difficulty: Difficulty = B) -> QuestionSpec:
    return QuestionSpec(QuestionType.MULTIPLE_CHOICE, difficulty, text, options, correct)


def _crit(*items: tuple[str, tuple[str, ...]]) -> tuple[Criterion, ...]:
    return tuple(Criterion(label, patterns) for label, patterns in items)


def _short(text: str, *criteria: tuple[str, tuple[str, ...]], difficulty: Difficulty = M) -> QuestionSpec:
    return QuestionSpec(QuestionType.SHORT_ANSWER, difficulty, text, criteria=_crit(*criteria))


def _code(text: str, *criteria: tuple[str, tuple[str, ...]], difficulty: Difficulty = M) -> QuestionSpec:
    return QuestionSpec(QuestionType.CODING, difficulty, text, criteria=_crit(*criteria))


BANK: dict[str, list[QuestionSpec]] = {
    "python": [
        _mcq(
            "Which statement about Python lists and tuples is correct?",
            (
                "Tuples are mutable and lists are not.",
                "Lists are mutable and tuples are immutable.",
                "Both are immutable.",
                "Neither can hold values of different types.",
            ),
            "B",
        ),
        _mcq("What does len({1, 2, 2, 3}) return?", ("4", "3", "2", "It raises an error."), "B"),
        _mcq(
            "What is the purpose of a Python virtual environment?",
            (
                "To make code run faster.",
                "To isolate a project's dependencies from other projects.",
                "To compile Python to machine code.",
                "To encrypt source files.",
            ),
            "B",
        ),
        _mcq(
            "Which construct makes a function a generator?",
            (
                "Using yield in the function body.",
                "Writing generate before def.",
                "Naming the function with lambda.",
                "Returning a list.",
            ),
            "A",
            M,
        ),
        _short(
            "Explain the difference between a list comprehension and a generator expression.",
            ("eager list", ("list in memory", "whole list", "eagerly", "eager", "all at once")),
            ("lazy evaluation", ("lazy", "lazily", "one at a time", "on demand", "as needed", "iterator")),
            ("memory", ("memory",)),
        ),
        _short(
            "What does the with statement do, and why is it useful when working with files?",
            ("context manager", ("context manager", "__enter__", "__exit__", "enter", "exit")),
            ("cleanup", ("close", "closes", "cleanup", "clean up", "released", "release")),
            ("exceptions", ("exception", "error", "even if", "fails")),
        ),
        _code(
            "Write a function count_words(text) that returns a dict mapping each lowercase word to its count. "
            "Handle empty input.",
            ("defines function", ("def count_words",)),
            ("lowercases", ("lower(",)),
            ("splits", ("split(",)),
            ("counts", ("+= 1", "+ 1", "counter(", ".get(", "defaultdict")),
            ("empty input", ("if not text", "not text", '== ""', "== ''", "strip()")),
            ("returns", ("return",)),
        ),
    ],
    "machine-learning": [
        _mcq(
            "What is overfitting?",
            (
                "The model performs well on training data but poorly on unseen data.",
                "The model performs poorly on both training and unseen data.",
                "Training takes too long.",
                "The model has too few parameters.",
            ),
            "A",
        ),
        _mcq(
            "Which data split gives the final, least biased estimate of model performance?",
            ("The training set", "The validation set", "The test set", "Any of them equally"),
            "C",
        ),
        _mcq(
            "Which metrics are most informative for a heavily imbalanced binary classification problem?",
            ("Accuracy alone", "Precision and recall (for example F1)", "Mean squared error", "R-squared"),
            "B",
            M,
        ),
        _mcq(
            "What does L2 regularization do?",
            (
                "Increases model complexity.",
                "Penalizes large weights to reduce overfitting.",
                "Removes the need for a test set.",
                "Speeds up data loading.",
            ),
            "B",
            M,
        ),
        _short(
            "Explain the bias-variance trade-off.",
            ("bias", ("bias", "underfit", "underfitting", "too simple")),
            ("variance", ("variance", "overfit", "overfitting", "too complex")),
            ("trade-off", ("trade-off", "tradeoff", "balance", "complexity")),
        ),
        _short(
            "Why is cross-validation used?",
            ("folds", ("fold", "folds", "k-fold", "splits", "subsets")),
            ("reliable estimate", ("reliable", "robust", "estimate", "generalization", "generalize")),
            ("not one split", ("one split", "single split", "limited data", "small dataset", "less variance")),
        ),
        _code(
            "Write a function train_test_split_indices(n, test_ratio, seed) that returns shuffled train and test "
            "index lists.",
            ("defines function", ("def train_test_split_indices",)),
            ("seeded shuffle", ("random.seed", "random.shuffle", "shuffle(", "permutation", "default_rng", "random(")),
            ("uses test_ratio", ("* test_ratio", "test_ratio *", "*test_ratio", "test_ratio*")),
            ("returns both", ("return",)),
        ),
    ],
    "llm-genai": [
        _mcq(
            "What is a token in the context of large language models?",
            (
                "A unit of text (such as a word piece) the model processes.",
                "A user password.",
                "A GPU core.",
                "A training epoch.",
            ),
            "A",
        ),
        _mcq(
            "What does the temperature setting control during generation?",
            (
                "The maximum output length.",
                "The randomness of next-token sampling.",
                "The model size.",
                "The number of GPUs used.",
            ),
            "B",
        ),
        _mcq(
            "What is a context window?",
            (
                "The maximum number of tokens the model can consider at once.",
                "The chat user interface.",
                "The response time limit.",
                "The size of the training dataset.",
            ),
            "A",
        ),
        _mcq(
            "Which technique gives an LLM access to up-to-date private documents without retraining it?",
            ("Pre-training from scratch", "Retrieval-augmented generation", "Raising the temperature", "Quantization"),
            "B",
        ),
        _short(
            "What is prompt injection and why does it matter for LLM applications?",
            ("overrides instructions", ("instruction", "instructions", "override", "overrides", "ignore")),
            ("untrusted input", ("untrusted", "user input", "external", "document", "web page", "malicious")),
            (
                "consequence",
                ("leak", "data", "exfiltrate", "unintended", "tool", "action", "harm", "attack", "security"),
            ),
        ),
        _short(
            "Why can an LLM hallucinate, and how can you reduce it?",
            ("plausible but wrong", ("plausible", "incorrect", "false", "made up", "fabricated", "not grounded")),
            (
                "next-token prediction",
                ("next token", "next-token", "probability", "probabilities", "predicts", "statistical"),
            ),
            (
                "mitigation",
                (
                    "retrieval",
                    "ground",
                    "grounding",
                    "grounded",
                    "citations",
                    "sources",
                    "verify",
                    "verification",
                    "rag",
                ),
            ),
        ),
        _code(
            "Write a function build_prompt(question, context_chunks) that returns a prompt string telling the "
            "model to answer only from the numbered context and to say so when the context is insufficient.",
            ("defines function", ("def build_prompt",)),
            ("numbers chunks", ("enumerate", "for", "range(")),
            (
                "only from context",
                ("only use", "only the context", "only from", "answer only", "using only", "based only"),
            ),
            (
                "insufficient context",
                (
                    "don't know",
                    "do not know",
                    "insufficient",
                    "not enough",
                    "cannot answer",
                    "can't answer",
                    "not contained",
                ),
            ),
            ("returns", ("return",)),
        ),
    ],
    "rag": [
        _mcq(
            "What are the two main phases of a RAG pipeline?",
            (
                "Training and fine-tuning.",
                "Retrieving relevant context and generating an answer conditioned on it.",
                "Tokenization and quantization.",
                "Compression and decompression.",
            ),
            "B",
        ),
        _mcq(
            "Why are documents split into chunks before embedding?",
            (
                "Embeddings cannot be computed for long text at all.",
                "So retrieval can return focused passages that fit the context window.",
                "To make the database smaller by deleting content.",
                "Vector databases require exactly 10 characters.",
            ),
            "B",
        ),
        _mcq(
            "Which similarity measure is commonly used to compare embeddings?",
            (
                "Cosine similarity",
                "Levenshtein file-name distance",
                "Hamming distance on file names",
                "Fibonacci distance",
            ),
            "A",
        ),
        _mcq(
            "Why attach source metadata (title, section) to each chunk?",
            (
                "It makes embeddings more accurate.",
                "It enables citations and traceability of answers.",
                "It reduces storage.",
                "It avoids the need to chunk.",
            ),
            "B",
            M,
        ),
        _short(
            "Explain why retrieval quality limits the answer quality of a RAG system.",
            ("generator sees retrieved context", ("context", "retrieved", "only sees", "only see")),
            (
                "bad retrieval -> bad answer",
                (
                    "irrelevant",
                    "missing",
                    "incorrect",
                    "hallucination",
                    "hallucinations",
                    "hallucinate",
                    "hallucinates",
                ),
            ),
            ("ways to improve", ("chunk", "rerank", "reranking", "top-k", "embedding", "hybrid", "filter")),
        ),
        _short(
            "What does a vector database store and what kind of query does it answer?",
            ("stores embeddings", ("embedding", "embeddings", "vector", "vectors")),
            ("similarity search", ("nearest", "similar", "similarity", "neighbor", "neighbour", "ann")),
            ("metadata filters", ("metadata", "payload", "filter", "filters")),
        ),
        _code(
            "Write a function cosine_similarity(a, b) for two equal-length lists of numbers that returns 0.0 if "
            "either vector has zero length (norm 0).",
            ("defines function", ("def cosine_similarity",)),
            ("dot product", ("zip(", "np.dot", "numpy.dot", "sum(")),
            ("norms", ("sqrt", "** 0.5", "**0.5", "norm(")),
            ("zero handling", ("== 0", "== 0.0", "return 0.0", "if not", "<= 0")),
            ("returns", ("return",)),
            difficulty=M,
        ),
    ],
    "ai-agents": [
        _mcq(
            "What distinguishes an AI agent from a single LLM call?",
            (
                "It loops: decide, call tools, observe results and continue until done.",
                "It uses a bigger model.",
                "It never uses prompts.",
                "It must run on a GPU.",
            ),
            "A",
        ),
        _mcq(
            "Why should an agent have a maximum number of steps or tool calls?",
            (
                "To make answers longer.",
                "To prevent runaway loops and unbounded cost.",
                "Because each tool works only once.",
                "To avoid needing a prompt.",
            ),
            "B",
        ),
        _mcq(
            "How should an agent handle a tool call with invalid arguments?",
            (
                "Execute it anyway.",
                "Validate against the tool's input schema and return a clear error.",
                "Retry forever.",
                "Ignore the schema.",
            ),
            "B",
            M,
        ),
        _mcq(
            "What is tool selection in an agent?",
            (
                "Choosing which tool, if any, suits the request.",
                "Selecting the GPU.",
                "Picking the training dataset.",
                "Choosing the font.",
            ),
            "A",
        ),
        _short(
            "Why should an agent treat tool results as untrusted data?",
            ("may contain instructions", ("injection", "instructions", "malicious", "untrusted")),
            ("not commands", ("not follow", "never follow", "data", "not instructions", "treat")),
            ("validate/bound", ("validate", "sanitize", "sanitise", "bound", "limit", "schema")),
        ),
        _short(
            "Describe how an agent should behave when a tool fails or times out.",
            ("handle gracefully", ("error", "handle", "gracefully", "catch", "fallback")),
            ("bounded retry/alternative", ("retry", "retries", "alternative", "fallback", "different tool")),
            ("report honestly", ("report", "tell the user", "inform", "disclose", "explain", "honest")),
        ),
        _code(
            "Write a function run_agent(request, tools, max_steps=5) that loops at most max_steps times, calls a "
            "tool from the tools dict and returns the collected results.",
            ("defines function", ("def run_agent",)),
            ("bounded loop", ("range(max_steps)", "< max_steps", "<= max_steps", "steps <")),
            ("looks up tool", ("tools[", "tools.get(")),
            ("error handling", ("try", "except")),
            ("returns", ("return",)),
            difficulty=M,
        ),
    ],
    "mcp": [
        _mcq(
            "What problem does the Model Context Protocol (MCP) address?",
            (
                "A standard way for AI applications to discover and call external tools and data sources.",
                "A new GPU architecture.",
                "A database engine.",
                "An image format.",
            ),
            "A",
        ),
        _mcq(
            "What can an MCP server expose to clients?",
            ("Tools, resources and prompts.", "Only GPU drivers.", "Only training checkpoints.", "Browser cookies."),
            "A",
        ),
        _mcq(
            "How does an MCP client learn which tools a server offers?",
            (
                "By hardcoding every tool name in the client.",
                "Through tool discovery: listing tools and their input schemas over the protocol.",
                "By reading the server's source code.",
                "By guessing.",
            ),
            "B",
        ),
        _mcq(
            "Which transport can a local MCP server use?",
            ("stdio, with the server as a subprocess.", "Only floppy disk.", "Only SMTP.", "Only FTP."),
            "A",
            M,
        ),
        _short(
            "Why is it useful that MCP tools declare input schemas?",
            ("validation", ("validate", "validation", "valid")),
            ("knows how to call", ("arguments", "parameters", "inputs", "how to call")),
            ("avoids bad calls", ("invalid", "invented", "errors", "strict", "contract", "mistakes")),
        ),
        _short(
            "Why not import a tool server's code directly into the application instead of using MCP?",
            ("boundary", ("boundary", "decouple", "decoupled", "separate", "independent", "isolation", "process")),
            ("reuse/standard", ("swap", "reuse", "any client", "standard", "standardized", "standardised")),
            ("discovery", ("discover", "discovery", "dynamic", "dynamically")),
        ),
        _code(
            "Write a function call_tool(tools, name, arguments) that looks up a tool by name, raises a clear error "
            "when it is unknown, and returns the tool's result.",
            ("defines function", ("def call_tool",)),
            ("looks up tool", ("tools[", "tools.get(", "in tools")),
            ("unknown tool error", ("raise",)),
            ("passes arguments", ("**arguments", "(arguments)", "arguments)")),
            ("returns", ("return",)),
        ),
    ],
    "docker": [
        _mcq(
            "What is the difference between a Docker image and a container?",
            (
                "An image is a read-only template; a container is a running instance of it.",
                "They are the same thing.",
                "A container is a template; an image is a running process.",
                "Images exist only on Windows.",
            ),
            "A",
        ),
        _mcq(
            "Which Dockerfile instruction sets the default command that runs when the container starts?",
            ("RUN", "CMD", "FROM", "COPY"),
            "B",
        ),
        _mcq(
            "Why copy requirements.txt and install dependencies before copying the rest of the source?",
            (
                "Docker requires that order.",
                "It uses the layer cache so dependencies are not reinstalled on every code change.",
                "It makes the image smaller by deleting code.",
                "It avoids needing a base image.",
            ),
            "B",
            M,
        ),
        _mcq(
            "What does a Docker volume provide?",
            (
                "Persistent storage outside the container's writable layer.",
                "More CPU.",
                "A new network protocol.",
                "A faster base image.",
            ),
            "A",
        ),
        _short(
            "Explain what docker compose is used for.",
            ("multiple services", ("multiple", "services", "several", "multi-container", "stack")),
            ("declarative file", ("yaml", "yml", "file", "declarative")),
            (
                "start together",
                ("together", "single command", "docker compose up", "network", "networking", "one command"),
            ),
        ),
        _short(
            "Why should secrets not be baked into a Docker image?",
            ("layers keep them", ("layer", "layers", "history", "inspect", "pull", "shared")),
            ("anyone with the image can read", ("anyone", "access", "read", "extract", "leak", "leaked", "exposed")),
            (
                "inject at runtime",
                (
                    "environment variable",
                    "environment variables",
                    "secret manager",
                    "secrets manager",
                    "runtime",
                    "docker secrets",
                    "inject",
                ),
            ),
        ),
        _code(
            "Write a Dockerfile for a Python 3.12 FastAPI app that installs requirements.txt and starts uvicorn "
            "on port 8000.",
            ("python base image", ("from python:3.12", "from python:3")),
            ("installs dependencies", ("pip install",)),
            ("copies source", ("copy . .", "copy . /", "copy app", "copy ./")),
            ("starts uvicorn", ("uvicorn",)),
            ("port 8000", ("8000",)),
        ),
    ],
    "fastapi": [
        _mcq(
            "How does FastAPI validate request bodies?",
            (
                "Using Pydantic models declared as type hints.",
                "By manually parsing every request.",
                "It does not validate.",
                "Using only regular expressions.",
            ),
            "A",
        ),
        _mcq(
            "What does Depends provide in FastAPI?",
            (
                "Dependency injection for things such as database sessions or authentication.",
                "A way to import modules.",
                "Database migrations.",
                "Template rendering only.",
            ),
            "A",
        ),
        _mcq(
            "Which HTTP status code is appropriate when a requested resource does not exist?",
            ("200", "404", "500", "301"),
            "B",
        ),
        _mcq(
            "What does FastAPI generate automatically from route definitions and type hints?",
            (
                "Interactive OpenAPI documentation (for example /docs).",
                "Machine code.",
                "A frontend application.",
                "A database schema.",
            ),
            "A",
        ),
        _short(
            "Explain the difference between a path parameter and a query parameter.",
            ("path param", ("path", "route", "url")),
            ("query param", ("query string", "?", "optional", "filter", "filters", "filtering")),
            ("usage", ("identify", "identifies", "resource", "id")),
        ),
        _short(
            "Why use response_model on an endpoint?",
            ("shapes output", ("filter", "filters", "shape", "shapes", "restrict", "limit")),
            ("avoids leaking fields", ("leak", "expose", "secret", "sensitive", "password", "private")),
            ("validation/docs", ("validate", "validates", "documentation", "docs", "schema", "openapi")),
        ),
        _code(
            "Write a FastAPI endpoint GET /items/{item_id} that returns an entry from a dict ITEMS or raises a " "404.",
            ("app", ("fastapi",)),
            ("route", ("@app.get(", "@router.get(")),
            ("path parameter", ("{item_id}",)),
            ("404", ("httpexception", "status_code=404", "404")),
            ("returns", ("return",)),
        ),
    ],
}


def available_skills() -> list[str]:
    return sorted(BANK)
