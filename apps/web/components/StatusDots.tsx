"use client";

import clsx from "clsx";
import { M1_STEPS, STEP_LABEL, type PipelineStep, type VideoStatus } from "@/lib/types";

interface Props {
  status: VideoStatus;
  currentStep: PipelineStep | null;
}

/** Sáu chấm thể hiện tiến trình pipeline — quy ước dùng ở mọi nơi trong app. */
export function StatusDots({ status, currentStep }: Props) {
  const index = currentStep ? M1_STEPS.indexOf(currentStep) : -1;
  const done = status === "ready" || status === "posted" || status === "scheduled";

  return (
    <div className="flex items-center gap-1">
      {M1_STEPS.map((step, i) => {
        let tone = "bg-[#333A48]";
        if (done || (index >= 0 && i < index)) tone = "bg-ok";
        else if (i === index) {
          if (status === "error") tone = "bg-err";
          else if (status === "review") tone = "bg-warn";
          else if (status === "running") tone = "bg-run animate-pulse";
          else tone = "bg-[#333A48]";
        }
        return (
          <span
            key={step}
            title={STEP_LABEL[step]}
            className={clsx("w-[7px] h-[7px] rounded-full", tone)}
          />
        );
      })}
    </div>
  );
}
