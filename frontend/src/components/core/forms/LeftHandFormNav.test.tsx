import { act, fireEvent, render, screen } from "@testing-library/react";

import LeftHandFormNav from "./LeftHandFormNav";

describe("LeftHandFormNav", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "#");
    window.requestAnimationFrame = (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    };
  });

  it("labels the navigation and focuses the selected form section", () => {
    render(
      <>
        <LeftHandFormNav
          title="Form sections"
          fields={[
            { href: "form-section-SectionA", text: "Section A" },
            { href: "form-section-SectionB", text: "Section B" },
          ]}
        />
        <fieldset
          id="form-section-SectionA"
          aria-label="Section A content"
          tabIndex={-1}
        />
        <fieldset
          id="form-section-SectionB"
          aria-label="Section B content"
          tabIndex={-1}
        />
      </>,
    );

    expect(
      screen.getByRole("navigation", { name: "Form sections" }),
    ).toBeInTheDocument();
    const sectionB = screen.getByRole("link", { name: "Section B" });
    fireEvent.click(sectionB);

    expect(sectionB).toHaveAttribute("aria-current", "location");
    expect(
      screen.getByRole("group", { name: "Section B content" }),
    ).toHaveFocus();
  });

  it("tracks browser hash navigation", () => {
    render(
      <LeftHandFormNav
        title="Form sections"
        fields={[{ href: "form-section-SectionA", text: "Section A" }]}
      />,
    );

    act(() => {
      window.history.replaceState(null, "", "#form-section-SectionA");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(screen.getByRole("link", { name: "Section A" })).toHaveAttribute(
      "aria-current",
      "location",
    );
  });
});
