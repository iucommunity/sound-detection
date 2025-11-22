import React, { useCallback } from 'react';
import Notification from './Notification';

const NotificationContainer = ({ notifications, removeNotification }) => {
  return (
    <div className="fixed top-6 right-6 z-[9999] flex flex-col gap-3 pointer-events-none">
      {notifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          removeNotification={removeNotification}
        />
      ))}
    </div>
  );
};

const NotificationItem = React.memo(({ notification, removeNotification }) => {
  const handleClose = useCallback(() => {
    removeNotification(notification.id);
  }, [notification.id, removeNotification]);

  return (
    <div className="pointer-events-auto relative">
      <Notification
        message={notification.message}
        type={notification.type}
        onClose={handleClose}
        duration={notification.duration}
      />
    </div>
  );
});

NotificationItem.displayName = 'NotificationItem';

export default NotificationContainer;

