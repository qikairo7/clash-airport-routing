function applyRoutingPolicy(config) {
  const policy = config["x-routing-policy"];
  if (!policy) return config;
  if (policy.version !== 1 || !Array.isArray(policy.groups)) throw new Error("路由策略版本或组列表无效");
  const groups = config["proxy-groups"];
  const providers = config["proxy-providers"];
  const escaped = (name) => "^" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "$";
  for (const entry of policy.groups) {
    const group = groups.find((item) => item.name === entry.name);
    if (!group || !["fallback", "url-test", "load-balance"].includes(group.type)) throw new Error("策略引用了不存在的自动组");
    if (entry.direct) {
      group.proxies = entry.direct.length ? entry.direct : ["REJECT"];
      delete group.use;
      delete group.filter;
      continue;
    }
    if (!Array.isArray(entry.layers)) throw new Error("策略缺少已排序的来源层");
    const names = [], sources = [];
    entry.layers.forEach((layer, index) => {
      const base = providers[layer.provider];
      if (!base || base.type !== "file" || !layer.names.length) throw new Error("策略来源缺失或候选为空");
      const name = "路由策略 " + entry.name + " " + index;
      const pattern = layer.names.map(escaped).join("`");
      providers[name] = {...base, filter: pattern, "health-check": {enable: true, url: group.url,
        "expected-status": group["expected-status"], interval: group.interval || 180,
        timeout: group.timeout || 5000, lazy: false}};
      sources.push(name);
      names.push(...layer.names);
    });
    delete group.proxies;
    delete group.filter;
    if (sources.length) {
      group.use = sources;
      group.filter = names.map(escaped).join("`");
    } else {
      delete group.use;
      group.proxies = ["REJECT"];
      group.type = "select";
    }
  }
  const blocked = new Set(policy.blocked_nodes || []);
  const blockedProviders = new Set(policy.blocked_providers || []);
  for (const name of blockedProviders) delete providers[name];
  for (const provider of Object.values(providers)) {
    if (blocked.size && provider.type === "file") {
      provider["exclude-filter"] = [provider["exclude-filter"], [...blocked].map(escaped).join("|")].filter(Boolean).join("|");
    }
  }
  config.proxies = config.proxies.filter((node) => !blocked.has(node.name));
  for (const group of groups) {
    if (group.proxies) group.proxies = group.proxies.filter((name) => !blocked.has(name));
    if (group.use) group.use = group.use.filter((name) => !blockedProviders.has(name));
    if ((!group.proxies || !group.proxies.length) && (!group.use || !group.use.length)) {
      group.proxies = ["REJECT"];
      group.type = "select";
    }
    group["empty-fallback"] = "REJECT";
  }
  delete config["x-routing-policy"];
  return config;
}

if (typeof module !== "undefined") module.exports = {applyRoutingPolicy};
