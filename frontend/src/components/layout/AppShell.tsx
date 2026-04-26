import { Link, Outlet, useLocation } from "react-router-dom";

import { Locale, locales, useI18n } from "../../app/i18n";

export function AppShell() {
  const { copy, locale, setLocale } = useI18n();
  const location = useLocation();
  const navigation = [
    { to: "/", ...copy.shell.nav.dashboard },
    { to: "/runs/new", ...copy.shell.nav.newRun },
    { to: "/runs", ...copy.shell.nav.runs },
    { to: "/scenarios", ...copy.shell.nav.scenarios },
    { to: "/kg", ...copy.shell.nav.kg },
    { to: "/guide", ...copy.shell.nav.guide },
    { to: "/settings/llm", ...copy.shell.nav.settings },
  ];

  function isActivePath(path: string) {
    if (path === "/") {
      return location.pathname === "/";
    }

    if (path === "/runs/new") {
      return location.pathname === "/runs/new";
    }

    if (path === "/runs") {
      return location.pathname === "/runs" || (location.pathname.startsWith("/runs/") && location.pathname !== "/runs/new");
    }

    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  }

  return (
    <div className="app-shell">
      <aside className="shell-rail" aria-label={copy.shell.navigationLabel}>
        <div className="shell-brand">
          <p className="brand-kicker">{copy.shell.brandKicker}</p>
          <h1 className="brand-title">{copy.shell.brandTitle}</h1>
          <div className="brand-meta">
            <span className="brand-chip">{copy.shell.chips.runtime}</span>
            <span className="brand-chip">{copy.shell.chips.graphAware}</span>
          </div>
        </div>

        <div className="shell-tools">
          <span className="shell-tools__label">{copy.language.label}</span>
          <div className="locale-switch" role="group" aria-label={copy.language.label}>
            {locales.map((item) => (
              <button
                key={item}
                className={item === locale ? "locale-button active" : "locale-button"}
                type="button"
                aria-pressed={item === locale}
                onClick={() => setLocale(item as Locale)}
              >
                {item === "zh-CN" ? copy.language.chinese : copy.language.english}
              </button>
            ))}
          </div>
        </div>

        <nav className="shell-nav">
          {navigation.map((item) => {
            const isCurrent = isActivePath(item.to);

            return (
              <Link
                key={item.to}
                to={item.to}
                className={isCurrent ? "active" : undefined}
                aria-current={isCurrent ? "page" : undefined}
              >
                <span className="nav-label">{item.label}</span>
                <span className="nav-meta">{item.meta}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
