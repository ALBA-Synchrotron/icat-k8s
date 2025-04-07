{{/*
Expand the name of the chart.
*/}}
{{- define "icat-k8s.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "icat-k8s.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "icat-k8s.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "icat-k8s.labels" -}}
helm.sh/chart: {{ include "icat-k8s.chart" . }}
{{ include "icat-k8s.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "icat-k8s.selectorLabels" -}}
app.kubernetes.io/name: {{ include "icat-k8s.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "icat-k8s.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "icat-k8s.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Setup script template for init containers
*/}}
{{- define "component-init-container-setup-script" }}
{{- $component := .component }}
{{- $values := .root.Values }}

{{- range $component.additionalArtifacts }}
  {{- $artifact := index $values.artifacts . }}
  {{- $repo := default $values.artifacts.rootRepositoryURL $artifact.repositoryURL }}

  {{- $savePath := "" }}
  {{- if eq $artifact.type "lib" }}
    {{- $savePath = "/opt/payara/libs/" }}
  {{- else if eq $artifact.type "deploy" }}
    {{- $savePath = "/opt/payara/deployments/" }}
    {{- else if eq $artifact.type "rar" }}
    {{- $savePath = "/opt/payara/rar/" }}
  {{- end }}

curl -o {{$savePath}}{{$artifact.filename}} {{ $repo }}{{$artifact.artifactPath}} && \
{{- end}}

{{- $repo := default $values.artifacts.rootRepositoryURL $values.artifacts.icatProjectComponents.repositoryURL }}
{{/* Fetch the component war file */}}
curl -o /opt/payara/deployments/{{$component.repoKey}}-{{$component.version}}.war {{ $repo }}{{ $values.artifacts.icatProjectComponents.baseArtifactPath }}{{ $component.repoKey }}/{{ $component.version }}/{{ $component.repoKey }}-{{ $component.version }}.war && \

curl -L -o /opt/payara/deployments/icat_k8s_setup_generator.py {{ $values.artifacts.initScripts.url }}/icat_k8s_setup_generator.py && \
curl -L -o /opt/payara/deployments/icat_k8s_setup_utils.py {{ $values.artifacts.initScripts.url }}/icat_k8s_setup_utils.py && \
cd /opt/payara/deployments/ && python /opt/payara/deployments/icat_k8s_setup_generator.py --component {{ $component.repoKey }}
{{- end }}

{{- define "hasItemInList" -}}
  {{- $item := .item -}}
  {{- $list := .list -}}
  {{- $found := false -}}
  {{- range $list }}
    {{- if eq . $item }}
      {{- $found = true -}}
      {{- break -}}
    {{- end }}
  {{- end }}
  {{- $found -}}
{{- end }}
