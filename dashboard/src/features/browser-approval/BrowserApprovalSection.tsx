/**
 * BrowserApprovalSection — 훅을 붙인 컨테이너.
 *
 * 화면(패널)과 자료(훅)를 나눠 둔 이유는 시험이다: 패널은 props 만으로 그릴 수 있어야 하고,
 * 그렇지 않으면 승인 UI 를 재려면 폴링·HTTP 를 함께 세워야 한다.
 */

import React from 'react';

import { BrowserApprovalPanel } from './BrowserApprovalPanel';
import { useBrowserApprovals } from './useBrowserApprovals';

export const BrowserApprovalSection: React.FC = () => {
  const state = useBrowserApprovals();
  return (
    <BrowserApprovalPanel
      requirements={state.requirements}
      decisions={state.decisions}
      pendingRequestId={state.pendingRequestId}
      error={state.error}
      onDecide={state.decide}
    />
  );
};

export default BrowserApprovalSection;
