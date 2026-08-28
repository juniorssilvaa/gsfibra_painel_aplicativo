import React, { useState, useContext } from 'react';
import { NotificationContext } from '../contexts/NotificationContext';
import { MessageCircle } from 'lucide-react';
import InternalChatPanel from './InternalChatPanel';

const InternalChatButton = () => {
  const [isOpen, setIsOpen] = useState(false);

  const notificationContext = useContext(NotificationContext);
  const { unreadCount, internalChatUnreadCount } = notificationContext;
  const topbarUnread = (internalChatUnreadCount || 0) + (unreadCount || 0);

  return (
    <>
      <button
        type="button"
        className="relative rounded-lg p-2 text-topbar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        title="Chat Interno"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        <MessageCircle className="h-5 w-5" />
        {topbarUnread > 0 && (
          <span
            className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#ef4444] px-1 text-[10px] font-bold leading-none text-white shadow-[0_0_8px_rgba(239,68,68,1)] ring-2 ring-[var(--topbar-background)]"
            aria-label={`${topbarUnread} mensagens não lidas`}
          >
            {topbarUnread > 9 ? '9+' : topbarUnread}
          </span>
        )}
      </button>

      <InternalChatPanel isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </>
  );
};

export default InternalChatButton;
