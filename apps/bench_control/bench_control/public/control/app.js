/* global Vue, csrf_token, site_name, user */
(function () {
  const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;

  async function call(method, args = {}) {
    const body = new URLSearchParams();
    body.set("cmd", method);
    Object.entries(args).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (Array.isArray(value)) body.set(key, value.join(","));
      else if (typeof value === "object") body.set(key, JSON.stringify(value));
      else body.set(key, String(value));
    });
    const res = await fetch("/api/method/" + method, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        Accept: "application/json",
        "X-Frappe-CSRF-Token": csrf_token || "",
      },
      body,
      credentials: "same-origin",
    });
    const data = await res.json();
    if (data.exc_type || data.exception || data._server_messages) {
      let msg = data.exception || data.exc_type || "Request failed";
      try {
        if (data._server_messages) {
          msg = JSON.parse(data._server_messages)
            .map((m) => JSON.parse(m).message)
            .join("\n");
        }
      } catch (_) {}
      throw new Error(msg);
    }
    return data.message;
  }

  createApp({
    setup() {
      const loading = ref(true);
      const overview = ref(null);
      const toast = ref("");
      const busy = ref(false);
      const selectedSite = ref("");
      const siteDetail = ref(null);
      const detailLoading = ref(false);
      const expandedJob = ref("");
      const jobDetail = ref(null);
      const pollTimer = ref(null);
      const errorLog = ref(null);
      const showLogs = ref(false);

      const newPassword = ref("");
      const hostNameEdit = ref("");
      const renameTo = ref("");
      const cloneTo = ref("");
      const backupWithFiles = ref(true);
      const backupBeforeDestructive = ref(true);
      const multiApp = ref("");
      const multiSites = ref([]);
      const jobFilter = ref({ status: "", site: "", operation: "" });
      const configForm = ref({
        developer_mode: 0,
        ignore_csrf: 0,
        allow_cors: "",
        mail_server: "",
        mail_port: "",
      });

      const form = ref({
        site_name: "",
        admin_password: "",
        host_name: "",
        apps: [],
        preset: "",
      });

      const availableApps = computed(() => overview.value?.available_apps || []);
      const sites = computed(() => overview.value?.sites || []);
      const bench = computed(() => overview.value?.bench || {});
      const catalog = computed(() => bench.value.app_catalog || []);
      const presets = computed(() => bench.value.presets || []);
      const queueDepth = computed(() => bench.value.queue_depth || {});
      const allJobs = computed(() => overview.value?.jobs || []);
      const jobs = computed(() => {
        return allJobs.value.filter((j) => {
          if (jobFilter.value.status && j.status !== jobFilter.value.status) return false;
          if (jobFilter.value.site && j.site_name !== jobFilter.value.site) return false;
          if (jobFilter.value.operation && j.operation !== jobFilter.value.operation) return false;
          return true;
        });
      });
      const pendingJobs = computed(() =>
        allJobs.value.filter((j) => j.status === "Queued" || j.status === "Running")
      );
      const operations = computed(() =>
        [...new Set(allJobs.value.map((j) => j.operation))].sort()
      );

      function statusClass(status) {
        if (status === "Success") return "ok";
        if (status === "Failed") return "danger";
        if (status === "Running") return "warn";
        return "muted";
      }

      function showToast(msg) {
        toast.value = msg;
        setTimeout(() => {
          if (toast.value === msg) toast.value = "";
        }, 4500);
      }

      async function refresh() {
        overview.value = await call("bench_control.api.overview");
        if (!selectedSite.value && overview.value.sites.length) {
          selectedSite.value = overview.value.sites[0].name;
        }
        loading.value = false;
        if (selectedSite.value) await loadSiteDetail(selectedSite.value, false);
        if (expandedJob.value) await loadJobDetail(expandedJob.value, false);
        if (showLogs.value) await loadErrorLog(false);
      }

      async function loadSiteDetail(name, showSpinner = true) {
        if (!name) return;
        if (showSpinner) detailLoading.value = true;
        try {
          siteDetail.value = await call("bench_control.api.get_site", { site_name: name });
          hostNameEdit.value = siteDetail.value.host_name || "";
          renameTo.value = "";
          cloneTo.value = "";
          configForm.value = {
            developer_mode: siteDetail.value.developer_mode || 0,
            ignore_csrf: siteDetail.value.ignore_csrf || 0,
            allow_cors: siteDetail.value.allow_cors || "",
            mail_server: siteDetail.value.mail_server || "",
            mail_port: siteDetail.value.mail_port || "",
          };
        } catch (err) {
          showToast(err.message || String(err));
        } finally {
          detailLoading.value = false;
        }
      }

      async function loadJobDetail(jobId) {
        try {
          jobDetail.value = await call("bench_control.api.get_job", { job_id: jobId });
        } catch (_) {}
      }

      async function loadErrorLog(spinner = true) {
        try {
          errorLog.value = await call("bench_control.api.error_log", {
            site_name: selectedSite.value || "",
            lines: 100,
          });
        } catch (err) {
          if (spinner) showToast(err.message || String(err));
        }
      }

      function selectSite(name) {
        selectedSite.value = name;
        loadSiteDetail(name);
      }

      async function toggleJob(jobId) {
        if (expandedJob.value === jobId) {
          expandedJob.value = "";
          jobDetail.value = null;
          return;
        }
        expandedJob.value = jobId;
        await loadJobDetail(jobId);
      }

      async function run(action, args) {
        busy.value = true;
        try {
          const result = await call(action, args);
          showToast(result.job_id ? "Job queued: " + result.job_id : "Done");
          if (result.job_id) expandedJob.value = result.job_id;
          await refresh();
        } catch (err) {
          showToast(err.message || String(err));
        } finally {
          busy.value = false;
        }
      }

      function applyPreset(id) {
        form.value.preset = id;
        const preset = presets.value.find((p) => p.id === id);
        if (!preset) return;
        form.value.apps = [...(preset.apps || [])];
      }

      async function createSite() {
        if (!form.value.site_name.trim()) return showToast("Site name is required");
        await run("bench_control.api.create_site", {
          site_name: form.value.site_name.trim().toLowerCase(),
          apps: form.value.apps,
          admin_password: form.value.admin_password || undefined,
          host_name: form.value.host_name || undefined,
        });
        form.value = { site_name: "", admin_password: "", host_name: "", apps: [], preset: "" };
      }

      function toggleApp(app) {
        const list = form.value.apps;
        const idx = list.indexOf(app);
        if (idx >= 0) list.splice(idx, 1);
        else list.push(app);
      }

      function toggleMultiSite(site) {
        const list = multiSites.value;
        const idx = list.indexOf(site);
        if (idx >= 0) list.splice(idx, 1);
        else list.push(site);
      }

      async function installApp(site, app) {
        await run("bench_control.api.install_app", { site_name: site, app_name: app });
      }

      async function installAppMulti() {
        if (!multiApp.value || !multiSites.value.length) {
          return showToast("Pick an app and at least one site");
        }
        await run("bench_control.api.install_app_multi", {
          app_name: multiApp.value,
          sites: multiSites.value,
        });
      }

      async function uninstallApp(site, app) {
        if (!confirm("Uninstall " + app + " from " + site + "?")) return;
        await run("bench_control.api.uninstall_app", { site_name: site, app_name: app });
      }

      async function migrateSite(site) {
        await run("bench_control.api.migrate_site", {
          site_name: site,
          backup_first: backupBeforeDestructive.value ? 1 : 0,
        });
      }

      async function migrateAll() {
        if (!confirm("Migrate all sites?")) return;
        await run("bench_control.api.migrate_all", {});
      }

      async function dropSite(site) {
        const typed = prompt("Type the site name to confirm drop:\n" + site);
        if (typed !== site) return showToast("Drop cancelled");
        await run("bench_control.api.drop_site", {
          site_name: site,
          confirm: 1,
          backup_first: backupBeforeDestructive.value ? 1 : 0,
        });
        if (selectedSite.value === site) selectedSite.value = "";
      }

      async function backupSite(site) {
        await run("bench_control.api.backup_site", {
          site_name: site,
          with_files: backupWithFiles.value ? 1 : 0,
        });
      }

      async function restoreSite(site, backupPath) {
        if (!confirm("Restore " + site + " from\n" + backupPath + "?")) return;
        const allow = site === site_name ? 1 : 0;
        if (allow && !confirm("This is the control site. Continue?")) return;
        await run("bench_control.api.restore_site", {
          site_name: site,
          backup_path: backupPath,
          allow_current: allow,
        });
      }

      async function clearCache(site) {
        await run("bench_control.api.clear_cache", { site_name: site });
      }

      async function setMaintenance(site, enabled) {
        await run("bench_control.api.set_maintenance", { site_name: site, enabled: enabled ? 1 : 0 });
      }

      async function resetPassword(site) {
        if (!newPassword.value || newPassword.value.length < 4) {
          return showToast("Password must be at least 4 characters");
        }
        if (!confirm("Reset Administrator password for " + site + "?")) return;
        await run("bench_control.api.reset_admin_password", {
          site_name: site,
          password: newPassword.value,
        });
        newPassword.value = "";
      }

      async function saveHostName(site) {
        await run("bench_control.api.set_host_name", {
          site_name: site,
          host_name: hostNameEdit.value || "",
        });
      }

      async function renameSite(site) {
        if (!renameTo.value.trim()) return showToast("New name required");
        if (!confirm("Rename " + site + " → " + renameTo.value + "?")) return;
        await run("bench_control.api.rename_site", {
          site_name: site,
          new_name: renameTo.value.trim().toLowerCase(),
        });
      }

      async function cloneSite(site) {
        if (!cloneTo.value.trim()) return showToast("Clone name required");
        await run("bench_control.api.clone_site", {
          site_name: site,
          new_name: cloneTo.value.trim().toLowerCase(),
        });
      }

      async function setDefault(site) {
        await run("bench_control.api.set_default_site", { site_name: site });
      }

      async function saveConfig(site) {
        await run("bench_control.api.set_site_config", {
          site_name: site,
          config: {
            developer_mode: configForm.value.developer_mode ? 1 : 0,
            ignore_csrf: configForm.value.ignore_csrf ? 1 : 0,
            allow_cors: configForm.value.allow_cors || null,
            mail_server: configForm.value.mail_server || null,
            mail_port: configForm.value.mail_port || null,
          },
        });
      }

      async function pingHealth(site) {
        busy.value = true;
        try {
          const health = await call("bench_control.api.site_health", { site_name: site });
          showToast(health.ok ? "Healthy · " + health.ping_ms + "ms" : "Unhealthy");
          await loadSiteDetail(site);
        } catch (err) {
          showToast(err.message || String(err));
        } finally {
          busy.value = false;
        }
      }

      async function toggleLogs() {
        showLogs.value = !showLogs.value;
        if (showLogs.value) await loadErrorLog();
      }

      function missingApps(site) {
        const installed = new Set(site.installed_apps || []);
        return availableApps.value.filter((a) => !installed.has(a));
      }

      function openPath(site, path) {
        const port = location.port ? ":" + location.port : "";
        window.open(location.protocol + "//" + site + port + path, "_blank");
      }

      watch(selectedSite, (name) => {
        if (name) loadSiteDetail(name);
      });

      onMounted(async () => {
        try {
          await refresh();
        } catch (err) {
          showToast(err.message || String(err));
          loading.value = false;
        }
        pollTimer.value = setInterval(() => {
          if (pendingJobs.value.length || document.visibilityState === "visible") {
            refresh().catch(() => {});
          }
        }, 3000);
      });

      onUnmounted(() => {
        if (pollTimer.value) clearInterval(pollTimer.value);
      });

      return {
        loading,
        overview,
        toast,
        busy,
        form,
        sites,
        jobs,
        pendingJobs,
        availableApps,
        catalog,
        presets,
        queueDepth,
        bench,
        selectedSite,
        siteDetail,
        detailLoading,
        expandedJob,
        jobDetail,
        newPassword,
        hostNameEdit,
        renameTo,
        cloneTo,
        backupWithFiles,
        backupBeforeDestructive,
        multiApp,
        multiSites,
        jobFilter,
        configForm,
        operations,
        errorLog,
        showLogs,
        site_name,
        user,
        statusClass,
        refresh,
        selectSite,
        toggleJob,
        createSite,
        applyPreset,
        toggleApp,
        toggleMultiSite,
        installApp,
        installAppMulti,
        uninstallApp,
        migrateSite,
        migrateAll,
        dropSite,
        backupSite,
        restoreSite,
        clearCache,
        setMaintenance,
        resetPassword,
        saveHostName,
        renameSite,
        cloneSite,
        setDefault,
        saveConfig,
        pingHealth,
        toggleLogs,
        loadErrorLog,
        missingApps,
        openPath,
      };
    },
    template: `
      <div class="app-shell">
        <header class="topbar">
          <div class="brand">
            <div class="brand-mark">Bench Control</div>
            <h1>Sites &amp; ops</h1>
            <p>Full bench control plane for this Docker image.</p>
          </div>
          <div class="meta">
            <div>{{ user }}</div>
            <div>control · {{ site_name }}</div>
            <div class="queue-line" v-if="queueDepth">
              queues s/d/l:
              {{ queueDepth.short ?? '—' }}/{{ queueDepth.default ?? '—' }}/{{ queueDepth.long ?? '—' }}
            </div>
            <div class="actions" style="margin-top:8px;justify-content:flex-end">
              <button class="btn" :disabled="busy" @click="migrateAll">Migrate all</button>
              <button class="btn" :disabled="busy" @click="toggleLogs">{{ showLogs ? 'Hide logs' : 'Error logs' }}</button>
            </div>
          </div>
        </header>

        <section v-if="showLogs" class="panel" style="margin-bottom:16px">
          <div class="panel-head">
            <h2>Error / bench logs {{ errorLog?.path ? '· ' + errorLog.path : '' }}</h2>
            <button class="btn" @click="loadErrorLog">Reload</button>
          </div>
          <pre class="log-pane">{{ errorLog?.content || 'Loading…' }}</pre>
        </section>

        <div v-if="loading" class="loading">Loading bench state…</div>

        <div v-else class="grid-3">
          <section class="panel">
            <div class="panel-head">
              <h2>Sites ({{ sites.length }})</h2>
              <button class="btn" :disabled="busy" @click="refresh">Refresh</button>
            </div>
            <div class="muted" style="margin-bottom:8px;font-size:0.8rem">
              default: {{ bench.default_site || '—' }}
            </div>
            <button
              v-for="site in sites"
              :key="site.name"
              class="site-row"
              :class="{ active: selectedSite === site.name }"
              @click="selectSite(site.name)"
            >
              <div class="site-row-top">
                <strong>{{ site.name }}</strong>
                <span class="badge" :class="site.maintenance_mode ? 'warn' : 'ok'">
                  {{ site.maintenance_mode ? 'maint' : 'live' }}
                </span>
              </div>
              <div class="site-row-meta muted">
                <span>{{ site.files_human || '—' }}</span><span>·</span><span>{{ site.db_human || '—' }}</span>
              </div>
              <div class="apps tight">
                <span v-for="app in site.installed_apps" :key="app" class="chip">{{ app }}</span>
              </div>
            </button>

            <div class="subpanel">
              <h3>App catalog</h3>
              <div v-for="app in catalog" :key="app.name" class="backup-row">
                <div>
                  <code>{{ app.name }}</code>
                  <div class="muted">v{{ app.version }}{{ app.route ? ' · ' + app.route : '' }}</div>
                </div>
              </div>
            </div>
          </section>

          <section class="panel detail-panel">
            <div v-if="!selectedSite" class="empty">Select a site</div>
            <div v-else-if="detailLoading && !siteDetail" class="empty">Loading…</div>
            <template v-else-if="siteDetail">
              <div class="panel-head">
                <h2>{{ siteDetail.name }}</h2>
                <div class="actions">
                  <button class="btn" @click="openPath(siteDetail.name, '/app')">Desk</button>
                  <button class="btn" v-if="siteDetail.installed_apps.includes('hr_portal')" @click="openPath(siteDetail.name, '/hr')">/hr</button>
                  <button class="btn" v-if="siteDetail.installed_apps.includes('bench_control')" @click="openPath(siteDetail.name, '/control')">/control</button>
                  <button class="btn" :disabled="busy" @click="pingHealth(siteDetail.name)">Health</button>
                </div>
              </div>

              <div class="stats">
                <div class="stat"><span class="stat-label">Health</span>
                  <span class="badge" :class="siteDetail.health?.ok ? 'ok' : 'danger'">{{ siteDetail.health?.ok ? 'OK' : 'FAIL' }}</span>
                </div>
                <div class="stat"><span class="stat-label">DB ping</span><span>{{ siteDetail.health?.ping_ms != null ? siteDetail.health.ping_ms + ' ms' : '—' }}</span></div>
                <div class="stat"><span class="stat-label">Files</span><span>{{ siteDetail.files_human || '—' }}</span></div>
                <div class="stat"><span class="stat-label">Database</span><span>{{ siteDetail.db_human || '—' }}</span></div>
              </div>

              <label class="check-inline">
                <input type="checkbox" v-model="backupBeforeDestructive" />
                Backup before migrate / drop
              </label>
              <label class="check-inline">
                <input type="checkbox" v-model="backupWithFiles" />
                Include files in backup
              </label>

              <div class="actions block">
                <button class="btn" :disabled="busy" @click="migrateSite(siteDetail.name)">Migrate</button>
                <button class="btn" :disabled="busy" @click="clearCache(siteDetail.name)">Clear cache</button>
                <button class="btn" :disabled="busy" @click="backupSite(siteDetail.name)">Backup</button>
                <button class="btn" :disabled="busy" @click="setMaintenance(siteDetail.name, !siteDetail.maintenance_mode)">
                  {{ siteDetail.maintenance_mode ? 'Exit maintenance' : 'Maintenance on' }}
                </button>
                <button class="btn" :disabled="busy || siteDetail.is_default" @click="setDefault(siteDetail.name)">
                  {{ siteDetail.is_default ? 'Default site' : 'Set default' }}
                </button>
                <button class="btn danger" :disabled="busy || siteDetail.is_current" @click="dropSite(siteDetail.name)">Drop</button>
              </div>

              <div class="subpanel">
                <h3>Apps</h3>
                <div class="apps">
                  <span v-for="app in (siteDetail.app_details || [])" :key="app.name" class="chip">
                    {{ app.name }} <span class="muted">v{{ app.version }}</span>
                  </span>
                </div>
                <div class="actions">
                  <select v-if="missingApps(siteDetail).length" class="btn" :disabled="busy"
                    @change="installApp(siteDetail.name, $event.target.value); $event.target.value=''">
                    <option value="">Install app…</option>
                    <option v-for="app in missingApps(siteDetail)" :key="app" :value="app">{{ app }}</option>
                  </select>
                  <button v-for="app in siteDetail.installed_apps.filter(a => a !== 'frappe')" :key="'u-'+app"
                    class="btn danger" :disabled="busy || (siteDetail.is_current && app === 'bench_control')"
                    @click="uninstallApp(siteDetail.name, app)">Remove {{ app }}</button>
                </div>
              </div>

              <div class="subpanel">
                <h3>host_name</h3>
                <div class="inline-form">
                  <input v-model="hostNameEdit" type="text" placeholder="https://desk.example.com" />
                  <button class="btn" :disabled="busy" @click="saveHostName(siteDetail.name)">Save</button>
                </div>
              </div>

              <div class="subpanel">
                <h3>Safe site config</h3>
                <div class="form-grid">
                  <label class="check-inline"><input type="checkbox" v-model="configForm.developer_mode" :true-value="1" :false-value="0" /> developer_mode</label>
                  <label class="check-inline"><input type="checkbox" v-model="configForm.ignore_csrf" :true-value="1" :false-value="0" /> ignore_csrf</label>
                  <label>allow_cors<input v-model="configForm.allow_cors" type="text" placeholder="* or origins" /></label>
                  <label>mail_server<input v-model="configForm.mail_server" type="text" /></label>
                  <label>mail_port<input v-model="configForm.mail_port" type="text" /></label>
                  <button class="btn" :disabled="busy" @click="saveConfig(siteDetail.name)">Save config</button>
                </div>
              </div>

              <div class="subpanel">
                <h3>Rename / clone</h3>
                <div class="inline-form" style="margin-bottom:8px">
                  <input v-model="renameTo" type="text" placeholder="new.site.name" />
                  <button class="btn" :disabled="busy || siteDetail.is_current" @click="renameSite(siteDetail.name)">Rename</button>
                </div>
                <div class="inline-form">
                  <input v-model="cloneTo" type="text" placeholder="clone.site.name" />
                  <button class="btn" :disabled="busy" @click="cloneSite(siteDetail.name)">Clone</button>
                </div>
              </div>

              <div class="subpanel">
                <h3>Reset Administrator password</h3>
                <div class="inline-form">
                  <input v-model="newPassword" type="password" placeholder="new password" />
                  <button class="btn" :disabled="busy" @click="resetPassword(siteDetail.name)">Reset</button>
                </div>
              </div>

              <div class="subpanel">
                <h3>Backups</h3>
                <div v-if="!(siteDetail.backups || []).length" class="empty">No backups yet.</div>
                <div v-for="b in siteDetail.backups" :key="b.name" class="backup-row">
                  <div>
                    <code>{{ b.name }}</code>
                    <div class="muted">{{ b.size_human }}</div>
                  </div>
                  <button
                    v-if="b.name.includes('database') || b.name.endsWith('.sql.gz') || b.name.endsWith('.sql')"
                    class="btn" :disabled="busy" @click="restoreSite(siteDetail.name, b.path)">Restore</button>
                </div>
              </div>
            </template>
          </section>

          <aside class="side-stack">
            <section class="panel">
              <h2>Create site</h2>
              <div class="form-grid">
                <label>
                  Preset
                  <select v-model="form.preset" @change="applyPreset(form.preset)">
                    <option value="">Custom</option>
                    <option v-for="p in presets" :key="p.id" :value="p.id">{{ p.label }}</option>
                  </select>
                </label>
                <label>Site name<input v-model="form.site_name" type="text" placeholder="tenant.localhost" /></label>
                <label>Admin password<input v-model="form.admin_password" type="password" /></label>
                <label>host_name<input v-model="form.host_name" type="text" placeholder="https://…" /></label>
                <label>
                  Apps
                  <div class="check-list">
                    <label v-for="app in availableApps" :key="app">
                      <input type="checkbox" :checked="form.apps.includes(app)" @change="toggleApp(app)" /> {{ app }}
                    </label>
                  </div>
                </label>
                <button class="btn primary" :disabled="busy" @click="createSite">Create site</button>
              </div>
            </section>

            <section class="panel">
              <h2>Install app on many sites</h2>
              <div class="form-grid">
                <label>
                  App
                  <select v-model="multiApp">
                    <option value="">Select…</option>
                    <option v-for="app in availableApps" :key="app" :value="app">{{ app }}</option>
                  </select>
                </label>
                <label>
                  Sites
                  <div class="check-list">
                    <label v-for="s in sites" :key="s.name">
                      <input type="checkbox" :checked="multiSites.includes(s.name)" @change="toggleMultiSite(s.name)" />
                      {{ s.name }}
                    </label>
                  </div>
                </label>
                <button class="btn" :disabled="busy" @click="installAppMulti">Install on selected</button>
              </div>
            </section>

            <section class="panel">
              <div class="panel-head">
                <h2>Jobs {{ pendingJobs.length ? '(' + pendingJobs.length + ' active)' : '' }}</h2>
              </div>
              <div class="job-filters">
                <select v-model="jobFilter.status">
                  <option value="">All status</option>
                  <option>Queued</option><option>Running</option><option>Success</option><option>Failed</option>
                </select>
                <select v-model="jobFilter.site">
                  <option value="">All sites</option>
                  <option v-for="s in sites" :key="s.name" :value="s.name">{{ s.name }}</option>
                  <option value="all">all</option>
                </select>
                <select v-model="jobFilter.operation">
                  <option value="">All ops</option>
                  <option v-for="op in operations" :key="op" :value="op">{{ op }}</option>
                </select>
              </div>
              <div class="jobs">
                <div v-if="!jobs.length" class="empty">No matching jobs.</div>
                <div v-for="job in jobs" :key="job.name" class="job" :class="{ open: expandedJob === job.name }" @click="toggleJob(job.name)">
                  <div class="job-top">
                    <code>{{ job.operation }}</code>
                    <span class="badge" :class="statusClass(job.status)">{{ job.status }}</span>
                  </div>
                  <div class="muted">{{ job.site_name }}<span v-if="job.app_name"> · {{ job.app_name }}</span></div>
                  <div class="error-box" v-if="job.error && expandedJob !== job.name">{{ job.error.slice(0, 240) }}</div>
                  <div v-if="expandedJob === job.name" class="job-log" @click.stop>
                    <pre>{{ (jobDetail && jobDetail.name === job.name) ? (jobDetail.output || jobDetail.error || '(no output)') : (job.output_tail || 'Loading…') }}</pre>
                  </div>
                </div>
              </div>
            </section>
          </aside>
        </div>

        <div v-if="toast" class="toast">{{ toast }}</div>
      </div>
    `,
  }).mount("#app");
})();
