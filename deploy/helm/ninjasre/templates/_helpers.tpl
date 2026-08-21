{{/*
Names, labels, and the two environment blocks every workload shares.

The environment blocks are here rather than repeated in each Deployment for the
reason a duplicated environment always eventually justifies: a setting added to
three of four workloads is a deployment where one component reads a different
configuration than the others, and the symptom is nothing until an incident.
*/}}

{{- define "ninjasre.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ninjasre.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "ninjasre.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ninjasre.labels" -}}
app.kubernetes.io/name: {{ include "ninjasre.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "ninjasre.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "ninjasre.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* The image reference, pinned by digest when one is given. */}}
{{- define "ninjasre.image" -}}
{{- $component := index . 1 -}}
{{- with index . 0 -}}
{{- if .Values.image.digest -}}
{{ .Values.image.registry }}/{{ .Values.image.repository }}/{{ $component }}@{{ .Values.image.digest }}
{{- else -}}
{{ .Values.image.registry }}/{{ .Values.image.repository }}/{{ $component }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Every setting the workloads share. The profile is fixed to `enterprise`: this
chart *is* the enterprise profile, and letting a values file say otherwise would
produce a deployment whose sandbox and concurrency did not match its shape.
*/}}
{{- define "ninjasre.env" -}}
- name: NINJASRE_DEPLOYMENT_PROFILE
  value: enterprise
- name: NINJASRE_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.postgres.urlSecret.name }}
      key: {{ .Values.postgres.urlSecret.key }}
- name: NINJASRE_DATABASE_ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.encryptionKey.secret.name }}
      key: {{ .Values.encryptionKey.secret.key }}
- name: NINJASRE_CREDENTIAL_PROXY_URL
  value: http://{{ include "ninjasre.fullname" . }}-proxy:{{ .Values.proxy.port }}
- name: NINJASRE_SANDBOX_PROFILE
  value: {{ .Values.sandbox.profile | quote }}
- name: NINJASRE_SANDBOX_NAMESPACE
  value: {{ .Values.sandbox.namespace | default .Release.Namespace | quote }}
- name: NINJASRE_SANDBOX_POOL_SIZE
  value: {{ .Values.sandbox.warmPoolSize | quote }}
{{- if .Values.sandbox.image }}
- name: NINJASRE_SANDBOX_IMAGE
  value: {{ .Values.sandbox.image | quote }}
{{- end }}
{{- if .Values.provider.id }}
- name: NINJASRE_LLM_PROVIDER
  value: {{ .Values.provider.id | quote }}
{{- end }}
{{- if .Values.provider.model }}
- name: NINJASRE_LLM_MODEL
  value: {{ .Values.provider.model | quote }}
{{- end }}
- name: NINJASRE_LOG_LEVEL
  value: {{ .Values.logging.level | quote }}
- name: NINJASRE_LOG_FORMAT
  value: {{ .Values.logging.format | quote }}
{{- if .Values.otel.enabled }}
- name: NINJASRE_OTEL_ENDPOINT
  value: {{ .Values.otel.endpoint | quote }}
{{- end }}
{{- if .Values.egress.airGapped }}
- name: NINJASRE_AIR_GAPPED
  value: "true"
{{- end }}
{{- if .Values.egress.allowlist }}
- name: NINJASRE_EGRESS_ALLOWLIST
  value: {{ join "," .Values.egress.allowlist | quote }}
{{- end }}
{{- if .Values.egress.caBundle.configMap }}
- name: NINJASRE_CA_BUNDLE
  value: /etc/ninjasre/tls/{{ .Values.egress.caBundle.key }}
{{- end }}
{{- if .Values.sso.enabled }}
- name: NINJASRE_SSO_ISSUER
  value: {{ .Values.sso.issuer | quote }}
- name: NINJASRE_SSO_CLIENT_ID
  value: {{ .Values.sso.clientId | quote }}
- name: NINJASRE_SSO_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.sso.clientSecretRef.name }}
      key: {{ .Values.sso.clientSecretRef.key }}
- name: NINJASRE_SSO_GROUPS_CLAIM
  value: {{ .Values.sso.groupsClaim | quote }}
{{- end }}
{{- end -}}

{{/*
The provider's credential — needed by the application, which is the one
workload that composes an investigation runtime and calls the provider. The
credential proxy stopped needing this once it stopped validating the
deployment's own provider (see `ninjasre.providerEnv`'s one remaining include
site, in app-deployment.yaml): handing it a model credential would spread a
secret to a process that never calls a model.

The environment-variable NAME depends on which provider is selected. A chart
cannot import `platform.startup.validation.PROVIDER_CREDENTIAL_ENV`, so the
mapping below restates it by hand; a contract test reads that constant and
checks this block against it, which is what keeps the two from drifting apart
silently rather than this comment. Ollama needs no credential at all and has
no branch here: mounting a secret reference for a provider that reads none
would be exactly the unneeded exposure this chart elsewhere avoids.
*/}}
{{- define "ninjasre.providerCredentialEnvName" -}}
{{- if eq .Values.provider.id "anthropic" -}}
ANTHROPIC_API_KEY
{{- else if eq .Values.provider.id "openai" -}}
OPENAI_API_KEY
{{- else if eq .Values.provider.id "azure_openai" -}}
AZURE_OPENAI_API_KEY
{{- else if eq .Values.provider.id "aws_bedrock" -}}
AWS_ACCESS_KEY_ID
{{- else if eq .Values.provider.id "google_gemini" -}}
GOOGLE_API_KEY
{{- else if eq .Values.provider.id "google_vertex_ai" -}}
GOOGLE_API_KEY
{{- else if eq .Values.provider.id "openrouter" -}}
OPENROUTER_API_KEY
{{- else if eq .Values.provider.id "nvidia_nim" -}}
NVIDIA_API_KEY
{{- else -}}
{{ fail (printf "provider.id %q has no known credential variable. Set it to one of: anthropic, openai, azure_openai, aws_bedrock, google_gemini, google_vertex_ai, openrouter, nvidia_nim, ollama." .Values.provider.id) }}
{{- end -}}
{{- end -}}

{{/*
The provider credential, for the workloads that compose the deployment.

Optional in both directions, and that is the design rather than a
convenience. Connecting a model provider is a first-run step: the operator
chooses one in the console and the key is stored in the vault, encrypted
with `encryptionKey.secret`. This block is the other way — for a deployment
that would rather be handed its provider than click one — so nothing renders
unless `provider.id` names one, and the Secret is referenced only when its
name is given. A chart that demanded a Secret nobody had created would
refuse to install a deployment that was configured correctly.

Ollama is skipped whatever else is set: a local model reads no vendor key.
*/}}
{{- define "ninjasre.providerEnv" -}}
{{- if and .Values.provider.id (ne .Values.provider.id "ollama") .Values.provider.credentialSecret.name }}
- name: {{ include "ninjasre.providerCredentialEnvName" . }}
  valueFrom:
    secretKeyRef:
      name: {{ .Values.provider.credentialSecret.name }}
      key: {{ .Values.provider.credentialSecret.key }}
{{- end -}}
{{- end -}}

{{/* The trust bundle mount, when the operator supplied one. */}}
{{- define "ninjasre.caVolumeMounts" -}}
{{- if .Values.egress.caBundle.configMap }}
- name: ca-bundle
  mountPath: /etc/ninjasre/tls
  readOnly: true
{{- end }}
{{- end -}}

{{- define "ninjasre.caVolumes" -}}
{{- if .Values.egress.caBundle.configMap }}
- name: ca-bundle
  configMap:
    name: {{ .Values.egress.caBundle.configMap }}
{{- end }}
{{- end -}}
