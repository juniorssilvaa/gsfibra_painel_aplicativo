import * as React from "react";
import { DayPicker } from "react-day-picker";
import { cn } from "@/lib/utils";

import "react-day-picker/style.css";

/**
 * Wrapper `.niohub-rdp-wrap` + regras em App.css garantem contraste no meio do intervalo
 * (popover/text-popover e herdávamos texto claro sobre faixa quase branca do day-picker).
 */
function Calendar({ className, ...props }) {
  return (
    <div className={cn("niohub-rdp-wrap", className)}>
      <DayPicker
        className={cn(
          "p-2",
          "[--rdp-accent-color:var(--primary)]",
          "[--rdp-range_start-date-background-color:var(--primary)]",
          "[--rdp-range_end-date-background-color:var(--primary)]",
          "[--rdp-range_start-color:#ffffff]",
          "[--rdp-range_end-color:#ffffff]",
        )}
        {...props}
      />
    </div>
  );
}

export { Calendar };
