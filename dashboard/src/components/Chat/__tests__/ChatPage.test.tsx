import { describe, expect, it, afterEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChatPage from '../ChatPage';
import { useChatStore } from '../../../stores/chatStore';

function renderChatPage() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>
  );
}

describe('ChatPage conversation workspace layout', () => {
  afterEach(() => {
    useChatStore.setState({
      messages: [],
      activeSession: null,
      isStreaming: false,
    });
  });

  it('renders the starting prompt, tools, and composer in the empty state', () => {
    renderChatPage();

    expect(screen.getByRole('heading', { name: '무엇을 만들어 볼까요?' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '메시지 입력' })).toBeInTheDocument();
    expect(screen.getByText('전체 액세스')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '검색' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '코드' })).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /모델 선택/i })).toBeInTheDocument();
    expect(screen.queryByText('5.6 Sol High')).toBeNull();
    expect(screen.getByRole('button', { name: '코드 살펴보기' })).toBeInTheDocument();
    expect(screen.getByLabelText('대화 기록 열기')).toBeInTheDocument();
    expect(screen.getByLabelText('환경 패널 토글')).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('button', { name: '메시지 전송' })).toBeDisabled();
  });

  it('renders Ssak-Ai environment rail with agent monitoring sections', () => {
    renderChatPage();
    fireEvent.click(screen.getByRole('button', { name: '환경 패널 토글' }));
    expect(screen.getByLabelText('환경 패널 토글')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('complementary', { name: '검사' })).toBeInTheDocument();
    expect(screen.getByText('에이전트 상태')).toBeInTheDocument();
    expect(screen.getByText('실시간 활동')).toBeInTheDocument();
    expect(screen.getByText('토큰 사용량')).toBeInTheDocument();
    expect(screen.getByText('파일 변경 추적')).toBeInTheDocument();
    expect(screen.getByText('에러 / 경고')).toBeInTheDocument();
  });

  it('renders the docked context bar and breadcrumb when a conversation exists', () => {
    useChatStore.setState({
      messages: [
        { role: 'user', content: '안녕하세요' },
        { role: 'assistant', content: '무엇을 도와드릴까요?' },
      ],
      activeSession: {
        id: 's1',
        title: 'Continuing Previous Agent Work',
        updatedAt: new Date().toISOString(),
        messages: [],
        conversationRevision: 0,
      },
    });
    renderChatPage();

    expect(screen.getByText('Continuing Previous Agent Work')).toBeInTheDocument();
    expect(screen.getByText('Ssak-Ai', { selector: '.crumb-project' })).toBeInTheDocument();
    expect(screen.getByText('로컬')).toBeInTheDocument();
    expect(screen.getByLabelText('현재 작업 환경')).toHaveTextContent('로컬');
    expect(screen.getByRole('region', { name: '대화 내용' })).toBeInTheDocument();
    expect(screen.queryByTestId('hero-headline')).not.toBeInTheDocument();
  });
});
