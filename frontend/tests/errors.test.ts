import { afterEach, describe, expect, it, vi } from "vitest";

import { APIError } from "../lib/api";
import { ClientError, localizeError, localizeErrorCode } from "../lib/errors";
import { catalogs, type MessageKey, type Translate } from "../lib/i18n/messages";

function translate(locale: "en-US" | "pt-BR"): Translate {
  return (key: MessageKey) => catalogs[locale][key];
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("localized error presentation", () => {
  it("maps stable client and API codes without exposing raw details", () => {
    expect(
      localizeError(new ClientError("media_required"), translate("en-US"), "errors.generic"),
    ).toBe("Select an audio or video file.");
    expect(
      localizeError(new ClientError("source_url_required"), translate("pt-BR"), "errors.generic"),
    ).toBe("Informe a URL de origem.");
    expect(
      localizeError(
        new ClientError("unsupported_media_type"),
        translate("pt-BR"),
        "errors.generic",
      ),
    ).toBe("Selecione um arquivo de áudio ou vídeo com tipo reconhecido.");
    expect(
      localizeError(
        new APIError("Unsafe URL detail", 400, "unsafe_remote_url"),
        translate("pt-BR"),
        "errors.generic",
      ),
    ).toBe("A URL remota não é permitida.");
  });

  it("uses HTTP status when an API error has no stable code", () => {
    expect(localizeError(new APIError("raw", 422), translate("en-US"), "errors.generic")).toBe(
      "The submitted data is invalid.",
    );
  });

  it("logs unknown detail and returns the contextual fallback", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const result = localizeError(
      new Error("socket detail"),
      translate("pt-BR"),
      "errors.libraryLoad",
    );

    expect(result).toBe("Não foi possível carregar a biblioteca.");
    expect(log).toHaveBeenCalledWith("Unhandled interface error", expect.any(Error));
  });

  it("localizes persisted job codes and falls back safely", () => {
    expect(
      localizeErrorCode("provider_execution_error", translate("en-US"), "errors.generic"),
    ).toBe("The provider could not complete the operation.");
    expect(localizeErrorCode("unknown", translate("en-US"), "errors.generic")).toBe(
      "Something went wrong. Try again.",
    );
  });
});
