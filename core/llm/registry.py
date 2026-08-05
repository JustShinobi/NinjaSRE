"""What each model can do, and what it costs, answerable before a call is made.

Two things in here are deliberate and will look like gaps until you read why.

**Most rows carry no pricing.** Only the reference provider's prices are a
single published number. Bedrock and Vertex price per region, Azure prices per
tenant agreement, OpenRouter prices per upstream and changes without notice, and
a local model has no price at all. Inventing a number for those produces a run
total that reads as authoritative and is wrong; ``None`` propagates through
``core.llm.usage`` as "unpriced", and the ledger reports how much of itself it
could not price. Operators supply the rest with :meth:`ModelRegistry.set_pricing`.

**Most rows are marked inferred.** A descriptor NinjaSRE ships is a starting
point, not a measurement: vendors change context windows and add features
between releases. ``preflight`` is what turns an inferred row into a confirmed
one, against the operator's own deployment.

Adding a provider is a row here plus an adapter under ``providers/`` — nothing
else, and ``tests/contract/llm/test_tenth_provider.py`` proves it.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from config.constants.llm import (
    DEFAULT_MODEL_ID,
    MODEL_PRICING_MAX_AGE_DAYS,
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_AZURE_OPENAI,
    PROVIDER_GOOGLE_GEMINI,
    PROVIDER_GOOGLE_VERTEX_AI,
    PROVIDER_NVIDIA_NIM,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)
from core.llm.usage import Pricing

#: The date the shipped pricing rows were taken from the vendor's published
#: table. Staleness is measured from here, not from a release date.
PRICING_SNAPSHOT = date(2026, 8, 4)


class UnknownModelError(LookupError):
    """A model nobody registered.

    Raised rather than defaulted. Falling back to some other model silently
    changes what an investigation ran on, and the run trace would say the wrong
    thing about how the answer was produced.
    """


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Everything the layer needs to know about one model before calling it."""

    model_id: str
    provider_id: str
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True
    supports_parallel_tool_calls: bool = True
    supports_prompt_cache: bool = False
    supports_reasoning_effort: bool = False
    pricing: Pricing | None = None
    pricing_as_of: date | None = None
    #: The provider-side name, when it differs from ``model_id``: an Azure
    #: deployment, a Bedrock inference profile, an OpenRouter route.
    deployment_id: str | None = None
    aliases: tuple[str, ...] = ()
    #: True when the row is NinjaSRE's best reading of the vendor's docs rather
    #: than something verified against the operator's own deployment.
    inferred: bool = True

    @property
    def wire_model_id(self) -> str:
        """Return the identifier to put on the wire."""
        return self.deployment_id or self.model_id

    def has_stale_pricing(
        self, as_of: date, max_age_days: int = MODEL_PRICING_MAX_AGE_DAYS
    ) -> bool:
        """Return whether the pricing on this row is old enough to distrust.

        A row with no pricing is not stale — it is unpriced, which the ledger
        already reports. Only a price somebody wrote down can go out of date.
        """
        if self.pricing is None or self.pricing_as_of is None:
            return False
        return as_of - self.pricing_as_of > timedelta(days=max_age_days)


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """What a provider is, independent of any one model."""

    provider_id: str
    display_name: str
    default_model_id: str
    is_local: bool = False
    #: Credentials never leave the vault; these are the *names* the resolver
    #: looks for, so a missing one is reported before a call rather than as a 401.
    required_credentials: tuple[str, ...] = ()


class ModelRegistry:
    """A mutable catalogue of models and providers.

    Mutable because an operator adds their own deployments, and because a tenth
    provider must be registrable without editing this file.
    """

    def __init__(self) -> None:
        self._models: dict[tuple[str, str], ModelDescriptor] = {}
        self._aliases: dict[tuple[str, str], str] = {}
        self._providers: dict[str, ProviderDescriptor] = {}
        self._defaults: dict[str, str] = {}

    # -- registration ---------------------------------------------------------

    def register(self, descriptor: ModelDescriptor, *, default: bool = False) -> None:
        """Add or replace one model row.

        The first model registered for a provider becomes its default unless a
        later row claims the slot with ``default=True``.
        """
        key = (descriptor.provider_id, descriptor.model_id)
        self._models[key] = descriptor
        for alias in descriptor.aliases:
            self._aliases[(descriptor.provider_id, alias)] = descriptor.model_id
        if default or descriptor.provider_id not in self._defaults:
            self._defaults[descriptor.provider_id] = descriptor.model_id

    def register_provider(self, descriptor: ProviderDescriptor) -> None:
        """Add or replace one provider row."""
        self._providers[descriptor.provider_id] = descriptor

    def set_pricing(
        self,
        provider_id: str,
        model_id: str,
        pricing: Pricing,
        *,
        as_of: date,
    ) -> None:
        """Attach operator-supplied pricing to an existing row.

        This is how a Bedrock region's or an Azure tenant's actual rates reach
        cost accounting without anyone guessing them here.
        """
        descriptor = self.get(provider_id, model_id)
        self.register(replace(descriptor, pricing=pricing, pricing_as_of=as_of))

    # -- lookup ---------------------------------------------------------------

    def get(self, provider_id: str, model_id: str) -> ModelDescriptor:
        """Return the descriptor for ``model_id``, resolving aliases.

        Raises:
            UnknownModelError: no row matches.
        """
        resolved = self._aliases.get((provider_id, model_id), model_id)
        descriptor = self._models.get((provider_id, resolved))
        if descriptor is None:
            raise UnknownModelError(
                f"no model {model_id!r} registered for provider {provider_id!r}"
            )
        return descriptor

    def find(self, provider_id: str, model_id: str) -> ModelDescriptor | None:
        """Return the descriptor, or ``None`` when nothing matches."""
        try:
            return self.get(provider_id, model_id)
        except UnknownModelError:
            return None

    def default_for_provider(self, provider_id: str) -> ModelDescriptor:
        """Return the model used when the caller names a provider but no model."""
        model_id = self._defaults.get(provider_id)
        if model_id is None:
            raise UnknownModelError(f"no models registered for provider {provider_id!r}")
        return self.get(provider_id, model_id)

    def for_provider(self, provider_id: str) -> tuple[ModelDescriptor, ...]:
        """Return every model registered for one provider."""
        return tuple(
            descriptor
            for (owner, _), descriptor in sorted(self._models.items())
            if owner == provider_id
        )

    def provider(self, provider_id: str) -> ProviderDescriptor | None:
        """Return the provider row, if one was registered."""
        return self._providers.get(provider_id)

    def provider_ids(self) -> tuple[str, ...]:
        """Return every provider that has at least one model."""
        return tuple(sorted({provider_id for provider_id, _ in self._models}))

    def all_models(self) -> tuple[ModelDescriptor, ...]:
        """Return every registered model, ordered for a stable report."""
        return tuple(descriptor for _, descriptor in sorted(self._models.items()))

    def __iter__(self) -> Iterator[ModelDescriptor]:
        """Iterate every registered model."""
        return iter(self.all_models())

    # -- health ---------------------------------------------------------------

    def stale_pricing(
        self, *, as_of: date, max_age_days: int = MODEL_PRICING_MAX_AGE_DAYS
    ) -> tuple[ModelDescriptor, ...]:
        """Return the rows whose pricing is older than ``max_age_days``."""
        return tuple(
            descriptor
            for descriptor in self.all_models()
            if descriptor.has_stale_pricing(as_of, max_age_days)
        )

    def inferred_models(self) -> tuple[ModelDescriptor, ...]:
        """Return the rows nobody has confirmed against a live deployment."""
        return tuple(descriptor for descriptor in self.all_models() if descriptor.inferred)


# --- The shipped catalogue ---------------------------------------------------

_ANTHROPIC_CACHE_READ_RATIO = 0.1
_ANTHROPIC_CACHE_WRITE_RATIO = 1.25


def _anthropic_pricing(input_per_million: float, output_per_million: float) -> Pricing:
    """Return Anthropic pricing with its published cache multipliers applied.

    A cache read is a tenth of an input token and a five-minute cache write is
    1.25 times one. Deriving them keeps the two from drifting apart when a base
    price is updated and someone forgets the other two lines.
    """
    return Pricing(
        input_per_million=input_per_million,
        output_per_million=output_per_million,
        cached_input_per_million=input_per_million * _ANTHROPIC_CACHE_READ_RATIO,
        cache_write_per_million=input_per_million * _ANTHROPIC_CACHE_WRITE_RATIO,
    )


_ANTHROPIC_MODELS: tuple[tuple[str, int, int, Pricing], ...] = (
    ("claude-opus-5", 1_000_000, 128_000, _anthropic_pricing(5.0, 25.0)),
    ("claude-sonnet-5", 1_000_000, 128_000, _anthropic_pricing(3.0, 15.0)),
    ("claude-opus-4-8", 1_000_000, 128_000, _anthropic_pricing(5.0, 25.0)),
    ("claude-haiku-4-5", 200_000, 64_000, _anthropic_pricing(1.0, 5.0)),
)

#: Conservative bounds for a hosted OpenAI-wire model whose row nobody has
#: confirmed. Under-stating a context window costs a truncation warning;
#: over-stating it costs a failed turn mid-investigation.
_UNVERIFIED_CONTEXT_WINDOW = 128_000
_UNVERIFIED_MAX_OUTPUT = 16_384

#: A local model's window is whatever the operator loaded it with. This is the
#: smallest window worth running an investigation on; ``preflight`` reads the
#: real one from the endpoint.
_LOCAL_CONTEXT_WINDOW = 32_768
_LOCAL_MAX_OUTPUT = 8_192


def _register_anthropic(registry: ModelRegistry) -> None:
    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_ANTHROPIC,
            display_name="Anthropic",
            default_model_id=DEFAULT_MODEL_ID,
            required_credentials=("api_key",),
        )
    )
    for model_id, context_window, max_output, pricing in _ANTHROPIC_MODELS:
        registry.register(
            ModelDescriptor(
                model_id=model_id,
                provider_id=PROVIDER_ANTHROPIC,
                context_window=context_window,
                max_output_tokens=max_output,
                supports_prompt_cache=True,
                supports_reasoning_effort=True,
                pricing=pricing,
                pricing_as_of=PRICING_SNAPSHOT,
                inferred=False,
            ),
            default=model_id == DEFAULT_MODEL_ID,
        )


def _register_openai_wire(registry: ModelRegistry) -> None:
    """Register the providers that speak the OpenAI chat-completions wire."""
    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_OPENAI,
            display_name="OpenAI",
            default_model_id="gpt-4.1",
            required_credentials=("api_key",),
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="gpt-4.1",
            provider_id=PROVIDER_OPENAI,
            context_window=1_000_000,
            max_output_tokens=32_768,
            supports_prompt_cache=True,
            supports_reasoning_effort=True,
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_AZURE_OPENAI,
            display_name="Azure OpenAI",
            default_model_id="gpt-4.1",
            required_credentials=("api_key", "endpoint", "deployment", "api_version"),
        )
    )
    registry.register(
        # Azure addresses a *deployment*, not a model. The deployment name is an
        # operator's choice, so the row carries the model it is expected to
        # serve and the deployment is resolved from configuration at call time.
        ModelDescriptor(
            model_id="gpt-4.1",
            provider_id=PROVIDER_AZURE_OPENAI,
            context_window=1_000_000,
            max_output_tokens=32_768,
            supports_prompt_cache=True,
            supports_reasoning_effort=True,
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_OPENROUTER,
            display_name="OpenRouter",
            default_model_id="anthropic/claude-sonnet-5",
            required_credentials=("api_key",),
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="anthropic/claude-sonnet-5",
            provider_id=PROVIDER_OPENROUTER,
            context_window=1_000_000,
            max_output_tokens=128_000,
            # Upstream-dependent, and OpenRouter does not promise either
            # through its own wire. Assume neither; the descriptor is what the
            # caller consults, so assuming yes would produce a rejected turn.
            supports_prompt_cache=False,
            supports_reasoning_effort=True,
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_NVIDIA_NIM,
            display_name="NVIDIA NIM",
            default_model_id="meta/llama-3.3-70b-instruct",
            required_credentials=("api_key",),
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="meta/llama-3.3-70b-instruct",
            provider_id=PROVIDER_NVIDIA_NIM,
            context_window=_UNVERIFIED_CONTEXT_WINDOW,
            max_output_tokens=_UNVERIFIED_MAX_OUTPUT,
            supports_structured_output=False,
            supports_parallel_tool_calls=False,
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_OLLAMA,
            display_name="Ollama / vLLM",
            default_model_id="llama3.1",
            is_local=True,
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="llama3.1",
            provider_id=PROVIDER_OLLAMA,
            context_window=_LOCAL_CONTEXT_WINDOW,
            max_output_tokens=_LOCAL_MAX_OUTPUT,
            supports_structured_output=False,
            supports_parallel_tool_calls=False,
        ),
        default=True,
    )


def _register_remaining(registry: ModelRegistry) -> None:
    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_AWS_BEDROCK,
            display_name="AWS Bedrock",
            default_model_id="anthropic.claude-sonnet-5",
            required_credentials=("region",),
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="anthropic.claude-sonnet-5",
            provider_id=PROVIDER_AWS_BEDROCK,
            context_window=1_000_000,
            max_output_tokens=128_000,
            # Converse exposes no native JSON mode; structured output goes
            # through tool coercion, which the adapter selects on this flag.
            supports_structured_output=False,
            supports_prompt_cache=True,
            supports_reasoning_effort=True,
            aliases=("claude-sonnet-5",),
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_GOOGLE_GEMINI,
            display_name="Google Gemini",
            default_model_id="gemini-2.5-pro",
            required_credentials=("api_key",),
        )
    )
    registry.register(
        ModelDescriptor(
            model_id="gemini-2.5-pro",
            provider_id=PROVIDER_GOOGLE_GEMINI,
            context_window=1_000_000,
            max_output_tokens=65_536,
            supports_prompt_cache=True,
        ),
        default=True,
    )

    registry.register_provider(
        ProviderDescriptor(
            provider_id=PROVIDER_GOOGLE_VERTEX_AI,
            display_name="Google Vertex AI",
            default_model_id="claude-sonnet-5",
            required_credentials=("project", "location"),
        )
    )
    registry.register(
        # Vertex serves Claude under the bare first-party identifier — no
        # provider prefix, unlike Bedrock.
        ModelDescriptor(
            model_id="claude-sonnet-5",
            provider_id=PROVIDER_GOOGLE_VERTEX_AI,
            context_window=1_000_000,
            max_output_tokens=128_000,
            supports_prompt_cache=True,
            supports_reasoning_effort=True,
        ),
        default=True,
    )
    registry.register(
        ModelDescriptor(
            model_id="gemini-2.5-pro",
            provider_id=PROVIDER_GOOGLE_VERTEX_AI,
            context_window=1_000_000,
            max_output_tokens=65_536,
            supports_prompt_cache=True,
        )
    )


def build_default_registry() -> ModelRegistry:
    """Return a fresh registry carrying the shipped catalogue."""
    registry = ModelRegistry()
    _register_anthropic(registry)
    _register_openai_wire(registry)
    _register_remaining(registry)
    return registry


@dataclass(slots=True)
class _RegistryHolder:
    """Holds the process-wide registry so tests can replace it."""

    registry: ModelRegistry = field(default_factory=build_default_registry)


_HOLDER = _RegistryHolder()


def default_registry() -> ModelRegistry:
    """Return the process-wide registry.

    One instance, because a model row an operator adds at start-up must be
    visible to every caller, and because ``preflight`` confirms rows in place.
    """
    return _HOLDER.registry


def reset_default_registry() -> ModelRegistry:
    """Rebuild the process-wide registry from the shipped catalogue.

    For tests that register a provider and must not leak it into the next one.
    """
    _HOLDER.registry = build_default_registry()
    return _HOLDER.registry


__all__ = [
    "PRICING_SNAPSHOT",
    "ModelDescriptor",
    "ModelRegistry",
    "Pricing",
    "ProviderDescriptor",
    "UnknownModelError",
    "build_default_registry",
    "default_registry",
    "reset_default_registry",
]
