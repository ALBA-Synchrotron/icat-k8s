# ICAT-k8s: Helm chart for ICAT

The ICAT project provides a metadata catalogue and related components to support experimental data management for
large-scale facilities, linking all aspects of the research lifecycle from proposal through to data and articles
publication.

More information on ICAT can be found [here](https://icatproject.org/).

## Introduction

This chart bootstraps all ICAT core components deployment on a [Kubernetes](https://kubernetes.io) cluster using
the [Helm](https://helm.sh) package manager.

> **Notice**: This Chart is meant to deploy ICAT components that support JakartaEE 10+ and Java 11+ with Payara 6.
> Deployments of older versions could be achieved through this Chart, but it is not directly supported.

## Prerequisites

- Kubernetes 1.30+
- Helm 3.17.0+
- An external MySQL / MariaDB database for ICAT and some of its components.

## Installing the Chart

To install the chart with the release name `my-release`, ideally you should make a copy of the default values file into
`values-my-release.yaml` and customize th deployment and each component's version and configuration to your needs.

After configuring the values file to your needs, the Chart can be installed as follows:

```console
helm install my-release icat-k8s -n NAMESPACE -f values-my-release.yaml
```

Any changes you make afterward to you values file can be applied as follows:

```console
helm upgrade my-release icat-k8s -n NAMESPACE -f values-my-release.yaml
```

> **Tip**: List all releases using `helm list`

You can uninstall and completely remove the Chart from your cluster with the following command:

```console
helm uninstall my-release -n NAMESPACE
```

##### Note: You need to substitute the placeholder

`NAMESPACE` with the name of namespace you want the Chart deployed at.

## Configuration and installation details

### Supported ICAT components

Currently, the following ICAT components are supported and have been tested with this chart.

| Name         | Versions |
|--------------|----------|
| icat.server  | 6.0.0+   |
| icat.lucene  | 2.0.0+   |
| icat.oaipmh  | 2.0.0+   |
| ids.server   | 2.0.0+   |
| authn.anon   | 3.0.0+   |
| authn.db     | 3.0.0+   |
| authn.ldap   | 3.0.0+   |
| authn.oidc   | 2.0.0+   |
| authn.simple | 3.0.0+   |

### Startup dependencies

The core components of ICAT need to be deployed in a certain order as some depend on others for stating up. This Chart
takes care of this aspect by making sure some component's deployment does not start before its dependencies. By default
the chart applies the following criteria:

- Authentication plugins: No dependencies on start.
- ICAT server: Waits for authentication plugins to be up and running.
- OAIPMH module and IDS server: Depend on icat.server.

Startup dependencies for any additional component you may add can be added by indicating the component's key and the
URL and port against which to test the availability.

```yaml
startupDependencies:
  - name: "icat-server"
    path: "/icat/version/"
    port: 8080
```

### Setup scripts and init-containers

The Chart leverages [init-containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) and a couple
of Python scripts to perform the artifact retrieval and configuration for each component prior their start.

Each deployed component will deploy two init-containers:

1. Retrieve component and required libraries artifacts for the application, and run setup script.
2. After the setup script has run, wait for startup dependencies to become available.

### Elastic APM integration

All deployed components can be monitoring with [Elastic](https://www.elastic.co/docs/reference/apm/agents/java) if the
option is enabled. If enabled, an APM agent is deployed alongside each component which forwards logs and resource usage
to your Elastic instance.

### Running own images and artifact repositories

By default, the Chart is provided configured to fetch container images, libraries and ICAT's app artifacts from their
original repositories, that is, Docker Hub, Apache Maven Central and
[ICAT's official repo](https://repo.icatproject.org/repo/). However, to reduce third-party dependency and mitigate
supply-chain risks, it is recommended to use your own repositories or at least configure proxied mirrors

The Chart gives the option to use specific images and repositories:

```yaml
images:
  container:
    micro: "docker.io/payara/micro:6.2025.2-jdk21"
    serverFull: "docker.io/payara/server-full:6.2025.3-jdk21"
  initContainers:
    # Must be image running as root (need to install curl)
    python: "docker.io/python:3.12.9-bullseye"
    curl: "docker.io/curlimages/curl:8.13.0"
  [ ... ]
artifacts:
  rootRepositoryURL: "https://repo.maven.apache.org/maven2"
  databaseConnector:
    artifactPath: "/org/mariadb/jdbc/mariadb-java-client/3.5.2/mariadb-java-client-3.5.2.jar"
    filename: "mariadb-java-client.jar"
    type: "lib"
    #repositoryURL: "https://youcanoverridethisifyouwant.nice"
  elasticAPM:
    artifactPath: "/co/elastic/apm/elastic-apm-agent/1.50.0/elastic-apm-agent-1.50.0.jar"
    filename: "elastic-apm-agent.jar"
    type: "lib"
    #repositoryURL: "https://youcanoverridethisifyouwant.nice"
  [ ... ]
```

## Parameters

### Ingress parameters

| Name                       | Description                                                 | Default value |
|----------------------------|-------------------------------------------------------------|---------------|
| `ingress.enabled`          | Deploy Ingress for ICAT with the Chart.                     | `false`       |
| `ingress.host`             | FQDN to use as the ingress' host.                           |               |
| `ingress.ingressClassName` | Name of an IngressClass cluster resource.                   |               |
| `ingress.tlsSecretName`    | Name of the Secret containing certificate for enabling TLS. |               |

### Container images parameters

| Name                           | Description                                      | Default value                                 |
|--------------------------------|--------------------------------------------------|-----------------------------------------------|
| `images.container.micro`       | Image for running Payara micro containers.       | `docker.io/payara/micro:6.2025.2-jdk21`       |
| `images.container.serverFull`  | Image for running Payara server-full containers. | `docker.io/payara/server-full:6.2025.3-jdk21` |
| `images.initContainers.python` | Python image for setup scripts.                  | `docker.io/python:3.12.9-bullseye`            |
| `images.initContainers.curl`   | curl image used for fetching artifacts..         | `docker.io/curlimages/curl:8.13.0`            |

### Artifacts parameters

| Name                                               | Description                                | Default value                                                                               |
|----------------------------------------------------|--------------------------------------------|---------------------------------------------------------------------------------------------|
| `artifacts.rootRepositoryURL`                      | Default repository for fetching artifacts. | `https://repo.maven.apache.org/maven2`                                                      |
| `artifacts.databaseConnector.artifactPath`         | DB connector's artifact path               | `/org/mariadb/jdbc/mariadb-java-client/3.5.2/mariadb-java-client-3.5.2.jar`                 |
| `artifacts.databaseConnector.filename`             | Filename of artifact inside container.     | `mariadb-java-client.jar`                                                                   |
| `artifacts.databaseConnector.type`                 | Artifact type.                             | `lib`                                                                                       |
| `artifacts.databaseConnector.repositoryURL`        | Repository override for specific artifact. |                                                                                             |
| `artifacts.elasticAPM.artifactPath`                | ElasticAPM's artifact path                 | `/co/elastic/apm/elastic-apm-agent/1.50.0/elastic-apm-agent-1.50.0.jar`                     |
| `artifacts.elasticAPM.filename`                    | Filename of artifact inside container.     | `elastic-apm-agent.jar`                                                                     |
| `artifacts.elasticAPM.type`                        | Artifact type.                             | `lib`                                                                                       |
| `artifacts.elasticAPM.repositoryURL`               | Repository override for specific artifact. |                                                                                             |
| `artifacts.idsStorageFile.artifactPath`            | IDS storage file artifact path             | `/org/icatproject/ids.storage_file/1.4.4/ids.storage_file-1.4.4.jar`                        |
| `artifacts.idsStorageFile.filename`                | Filename of artifact inside container.     | `ids-storage_file.jar`                                                                      |
| `artifacts.idsStorageFile.type`                    | Artifact type.                             | `lib`                                                                                       |
| `artifacts.idsStorageFile.repositoryURL`           | Repository override for specific artifact. | `https://repo.icatproject.org/repo/`                                                        |
| `artifacts.icatProjectComponents.baseArtifactPath` | Base path of ICAT components artifacts.    | `/org/icatproject/`                                                                         |
| `artifacts.icatProjectComponents.repositoryURL`    | Repository override for ICAT artifacts.    | `https://repo.icatproject.org/repo`                                                         |
| `artifacts.initScripts.url`                        | URL of setup scripts.                      | `https://raw.githubusercontent.com/ALBA-Synchrotron/icat-k8s/refs/heads/main/setup_scripts` |

### General configuration parameters

| Name                          | Description                                                                                                                | Default value   |
|-------------------------------|----------------------------------------------------------------------------------------------------------------------------|-----------------|
| `imagePullSecretName`         | Name of secret with credentials for private image registry.                                                                |                 |
| `deploymentPriorityClassName` | [Priority classname](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/) for the deployment. |                 |
| `timezone`                    | Set's TZ in all containers.                                                                                                | `Europe/Madrid` |

### ElasticAPM parameters

| Name                                   | Description                                   | Default value                                                                                                                                           |
|----------------------------------------|-----------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| `elasticAPM.enabled`                   | Toggle ElasticAPM integration                 | `false`                                                                                                                                                 |
| `elasticAPM.agentJarPath`              | Path to APM's jar file inside container.      | `/opt/payara/libs/elastic-apm-agent.jar`                                                                                                                |
| `elasticAPM.packageNames`              | Package names to monitor.                     | `es.cells.icat.authn_alba,org.icatproject.authn_anon,org.icatproject.authn_db,org.icatproject.icat_oaipmh,org.icatproject.exposed,org.icatproject.ids"` |
| `elasticAPM.apm.serviceNamePrefix`     | Prefix to add to each component's service.    | `icat-core`                                                                                                                                             |
| `elasticAPM.apm.apmLogSending`         | Toggle APM log sending feature.               | `true`                                                                                                                                                  |
| `elasticAPM.apm.secretTokenSecretName` | Name of secret containing APM's secret token. | `elastic-apm-token`                                                                                                                                     |
| `elasticAPM.apm.environment`           | APM's reporting environment name.             | `test`                                                                                                                                                  |

### ICAT components parameters (`components`)

| Name                     | Description                                                                                                                | Default value |
|--------------------------|----------------------------------------------------------------------------------------------------------------------------|---------------|
| `name`                   | Name of component (format e.g.: 'authn-anon')                                                                              |               |
| `repoKey`                | Name of component in repo (format e.g.: 'authn.anon)                                                                       |               |
| `version`                | Version of the component.                                                                                                  |               |
| `replicas`               | Replicas for the component.                                                                                                | 1             |
| `resources`              | Resource limits and requests for the component.                                                                            |               |
| `readinessProbe`         | [Readiness probe](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) for the component. |               |
| `livenessProbe`          | [Liveness probe](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) for the component.  |               |
| `mountInstrumentStorage` | Toggle instrument's storage mount.                                                                                         |               |
| `setupProperties`        | Content of `setup.properties` file of the component.                                                                       |               |
| `runProperties`          | Content of `run.properties` file of the component.                                                                         |               |
| `addtitionalArtifacts`   | List of additional artifacts required by the component (e.g. db connector).                                                |               |
| `logbackXml`             | Content of `logback.xml` file of the component.                                                                            |               |
| `xslt`                   | Content of the XSLT files used by the OAIPMH module. It is a key-value field, each key is the xslt filename.               |               |
| `startupDependencies`    | Services for which to wait before starting the component.                                                                  |               |
| `cacheDir`               | Mount directory for cache (only IDS).                                                                                      |               |
| `synonymTxt`             | Content of `synonym.txt` file for the OAIPMH module.                                                                       |               |

### NFS storage parameters (`instrumentStorage.storageList`)

| Name           | Description                        | Default value |
|----------------|------------------------------------|---------------|
| `name`         | Name of the volume.                |               |
| `mountPath`    | Volume's mount path in container.  |               |
| `readOnly`     | Toggle volume writting access.     |               |
| `nfs.server`   | NFS server.                        |               |
| `nfs.path`     | Path in NFS server.                |               |
| `nfs.readOnly` | Toggle write access in NFS server. |               |

## License

Copyright (C) 2026 ALBA Synchrotron

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.