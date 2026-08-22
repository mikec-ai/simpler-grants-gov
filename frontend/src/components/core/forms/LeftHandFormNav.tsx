"use client";

import React, { useEffect, useMemo, useState } from "react";

const LeftHandFormNav = ({
  fields,
  title,
}: {
  fields: { href: string; text: string }[];
  title: string;
}) => {
  const [currentHref, setCurrentHref] = useState("");

  useEffect(() => {
    const syncFromHash = () => setCurrentHref(window.location.hash.slice(1));
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  const Links = useMemo(
    () =>
      fields.map(({ text, href }) => (
        <li className="usa-in-page-nav__item" key={text}>
          <a
            className="usa-link usa-in-page-nav__link"
            href={`#${href}`}
            aria-current={currentHref === href ? "location" : undefined}
            onClick={() => {
              setCurrentHref(href);
              window.requestAnimationFrame(() => {
                document.getElementById(href)?.focus();
              });
            }}
          >
            {text}
          </a>
        </li>
      )),
    [currentHref, fields],
  );
  return (
    fields.length > 0 && (
      <aside
        className="usa-in-page-nav maxw-card order-1 margin-left-0 desktop:margin-right-5 overflow-auto"
        data-testid="InPageNavigation"
      >
        <nav className="usa-in-page-nav__nav padding-x-0" aria-label={title}>
          <h4 className="usa-in-page-nav__heading">{title}</h4>
          <ul className="usa-in-page-nav__list">{Links}</ul>
        </nav>
      </aside>
    )
  );
};

export default LeftHandFormNav;
